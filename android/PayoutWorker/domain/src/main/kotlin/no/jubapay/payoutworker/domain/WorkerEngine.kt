package no.jubapay.payoutworker.domain

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import kotlinx.coroutines.withContext

/** One engine per application. Room's active slot is the durable cross-entry-point fence. */
class WorkerEngine(private val store: AttemptStore, private val backend: Backend,
 private val provider: ProviderAdapter, private val readiness: Readiness,
 private val config: () -> DeviceConfig, private val clock: TimeSource = TimeSource { System.currentTimeMillis() }) {
 private val execution = Mutex()
 private val uploads = Mutex()
 private val mutableState = MutableStateFlow(DeviceState.PAUSED)
 val state: StateFlow<DeviceState> = mutableState
 @Volatile private var paused = true
 @Volatile private var draining = false
 fun start() { paused=false; draining=false }
 fun pause() { paused=true; mutableState.value=DeviceState.PAUSED }
 fun drain() { draining=true; mutableState.value=DeviceState.PAUSED }
 // Never cancel a provider operation after submission; finish confirmation tracking.
 fun emergencyStop() { pause() }
 suspend fun recover() = execution.withLock {
  for (a in store.all().filter { !it.phase.confirmed }) {
   if (a.phase != Phase.RECONCILIATION_REQUIRED)
    store.transition(a.assignment.attemptId,a.phase,Phase.RECONCILIATION_REQUIRED,
     Evidence(ResultKind.UNKNOWN, if(a.submissionAt != null) "RECOVERY_POSSIBLE_SUBMISSION" else "RECOVERY_NO_AUTOMATIC_REEXECUTION"))
   store.quarantine("UNFINISHED_ATTEMPT")
  }
  if(store.quarantineReason()!=null) mutableState.value=DeviceState.QUARANTINED
 }
 suspend fun flush() = uploads.withLock {
  for(e in store.pending()) {
   try { if(!backend.upload(e)) throw WorkerFailure.Conflict(); store.acknowledge(e.eventId) }
   catch(e: WorkerFailure.Conflict) { store.quarantine("EVENT_CONFLICT"); throw e }
  }
 }
 suspend fun reconcile() = execution.withLock {
  flush()
  for(a in store.all().filter { it.phase == Phase.RECONCILIATION_REQUIRED || it.phase == Phase.UNKNOWN }) {
   if(a.phase==Phase.UNKNOWN) store.transition(a.assignment.attemptId,a.phase,Phase.RECONCILIATION_REQUIRED,a.evidence)
   val answer=backend.reconcile(a)
   if(answer.resolved && !answer.auditId.isNullOrBlank() && answer.evidence != null) {
    val proof=provider.interpret(a.assignment,answer.evidence)
    if(proof.kind!=ResultKind.UNKNOWN) store.transition(a.assignment.attemptId,Phase.RECONCILIATION_REQUIRED,
     if(proof.kind==ResultKind.SUCCESS_CONFIRMED) Phase.CONFIRMED_SUCCESS else Phase.CONFIRMED_NOT_PAID,proof)
   }
  }
  flush(); store.clearQuarantineAfterReconciliation()
 }
 suspend fun cycle() = execution.withLock {
  flush()
  if(store.quarantineReason()!=null) { mutableState.value=DeviceState.QUARANTINED; backend.heartbeat(DeviceState.QUARANTINED); return@withLock }
  val control=backend.heartbeat(if(paused||draining) DeviceState.PAUSED else DeviceState.AVAILABLE)
  if(control.revoked) { pause(); throw WorkerFailure.Authentication() }
  if(paused||draining||control.paused||control.drain) { mutableState.value=DeviceState.PAUSED; return@withLock }
  if(!store.hasCapacity() || readiness.checks().any { !it.ready }) { mutableState.value=DeviceState.DEGRADED; return@withLock }
  mutableState.value=DeviceState.AVAILABLE
  val job=backend.claim() ?: return@withLock
  val a=try { store.accept(job) } catch(e: WorkerFailure.Conflict) { store.quarantine("ASSIGNMENT_CONFLICT"); throw e }
  if(a.phase!=Phase.RECEIVED) { flush(); return@withLock }
  mutableState.value=DeviceState.BUSY
  try {
   job.validate(config(),clock.now())
   store.transition(job.attemptId,Phase.RECEIVED,Phase.VALIDATED)
   backend.acknowledgeAssignment(job)
   store.transition(job.attemptId,Phase.VALIDATED,Phase.READY)
   check(provider.providerId==job.providerId && provider.flowVersion==job.flowVersion)
   if(provider.readiness(job).any { !it.ready }) throw WorkerFailure.NotReady()
   store.transition(job.attemptId,Phase.READY,Phase.PREPARING)
   provider.prepare(job)
   job.validate(config(),clock.now())
   if(paused||draining||readiness.checks().any { !it.ready } || provider.readiness(job).any { !it.ready }) throw WorkerFailure.NotReady()
   val controlNow=backend.heartbeat(DeviceState.BUSY)
   if(controlNow.paused||controlNow.drain||controlNow.revoked) throw WorkerFailure.NotReady()
   val auth=backend.authorize(job)
   if(paused||draining||auth.attemptId!=job.attemptId||auth.payloadHash!=job.payloadHash||
    clock.now()+1_000>=auth.expiresAt||clock.now()+1_000>=job.executionExpiresAt) throw WorkerFailure.Protocol("AUTHORIZATION_INVALID")
   // This transaction consumes auth + commits SUBMISSION_POSSIBLE + event. Failure means NO submission.
   store.transition(job.attemptId,Phase.PREPARING,Phase.SUBMISSION_POSSIBLE,authorization=auth)
   // The authorization can expire during a slow disk write. Never execute in that case.
   if(clock.now()>=auth.expiresAt) throw WorkerFailure.Protocol("AUTHORIZATION_EXPIRED_AFTER_COMMIT")
   store.transition(job.attemptId,Phase.SUBMISSION_POSSIBLE,Phase.AWAITING_CONFIRMATION)
   if(paused || draining || clock.now()>=auth.expiresAt || clock.now()>=job.executionExpiresAt) throw WorkerFailure.Protocol("SUBMISSION_WINDOW_CLOSED")
   val proof=provider.interpret(job,provider.executeSubmission(job))
   val next=when(proof.kind){ResultKind.SUCCESS_CONFIRMED->Phase.CONFIRMED_SUCCESS;ResultKind.NOT_PAID_CONFIRMED->Phase.CONFIRMED_NOT_PAID;ResultKind.UNKNOWN->Phase.UNKNOWN}
   store.transition(job.attemptId,Phase.AWAITING_CONFIRMATION,next,proof)
   if(next==Phase.UNKNOWN) store.quarantine("UNRESOLVED_SUBMISSION")
  } catch(failure: Exception) {
   withContext(NonCancellable) {
    val current=store.get(job.attemptId)
    if(current!=null && !current.phase.confirmed) {
     if(current.submissionAt!=null || current.phase.uncertain) {
      if(current.phase in setOf(Phase.SUBMISSION_POSSIBLE,Phase.AWAITING_CONFIRMATION))
       store.transition(job.attemptId,current.phase,Phase.UNKNOWN,Evidence(ResultKind.UNKNOWN,"TRACKING_INTERRUPTED"))
      store.quarantine("UNRESOLVED_SUBMISSION")
     } else {
      provider.cancelBeforeSubmission(job)
      store.transition(job.attemptId,current.phase,Phase.CONFIRMED_NOT_PAID,Evidence(ResultKind.NOT_PAID_CONFIRMED,"LOCAL_NO_SUBMISSION"))
     }
    }
   }
   if(failure is CancellationException) throw failure
  }
  flush()
  mutableState.value=if(store.quarantineReason()!=null) DeviceState.QUARANTINED else if(paused||draining) DeviceState.PAUSED else DeviceState.AVAILABLE
 }
}
