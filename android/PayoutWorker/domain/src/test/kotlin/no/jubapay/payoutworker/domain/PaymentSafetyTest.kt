package no.jubapay.payoutworker.domain

import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.*
import org.junit.Test

class PaymentSafetyTest {
 private fun job(): Assignment {val a=Assignment("payout","attempt","device",1,"simulator","account",-1,"+252610000000","MSISDN",1000,"USD","","sim-v1",100000,100000,"correlation");return a.copy(payloadHash=a.immutableHash())}
 private val config=DeviceConfig("device","simulator","account",-1)
 class Store: AttemptStore {
  override val changes=MutableStateFlow<List<Attempt>>(emptyList())
  var a:Attempt?=null;var q:String?=null;var failBoundary=false;val outbox=mutableListOf<Event>()
  override suspend fun all()=listOfNotNull(a)
  override suspend fun get(id:String)=a
  override suspend fun accept(job:Assignment):Attempt {a?.let{if(it.assignment!=job)throw WorkerFailure.Conflict();return it};return Attempt(job,Phase.RECEIVED,1,1).also{a=it}}
  override suspend fun transition(id:String,expected:Phase,next:Phase,evidence:Evidence?,authorization:Authorization?):Attempt {
   if(next==Phase.SUBMISSION_POSSIBLE && failBoundary)throw IllegalStateException("disk full")
   val old=a!!;check(old.phase==expected && expected.permits(next))
   return old.copy(phase=next,sequence=old.sequence+1,evidence=evidence?:old.evidence,authorizationId=authorization?.id?:old.authorizationId,
    submissionAt=if(next==Phase.SUBMISSION_POSSIBLE)1 else old.submissionAt).also{a=it}
  }
  override suspend fun pending()=outbox.toList()
  override suspend fun acknowledge(eventId:String){outbox.removeAll{it.eventId==eventId}}
  override suspend fun quarantine(reason:String){q=reason}
  override suspend fun quarantineReason()=q
  override suspend fun clearQuarantineAfterReconciliation(){}
  override suspend fun hasCapacity()=q==null
 }
 class Server(var job:Assignment):Backend {
  var authorizations=0;var revoked=false;var expiry=90000L;var uploadAttempts=0
  override suspend fun heartbeat(state:DeviceState)=Control(revoked=revoked)
  override suspend fun claim()=job
  override suspend fun acknowledgeAssignment(job:Assignment){}
  override suspend fun authorize(job:Assignment):Authorization {authorizations++;return Authorization("auth",job.attemptId,job.payloadHash,expiry)}
  override suspend fun upload(event:Event):Boolean {uploadAttempts++;return true}
  override suspend fun reconcile(attempt:Attempt)=Reconciliation(false)
 }
 class Provider:ProviderAdapter {
  var submissions=0;var throwAfter=false;var reject=false;var throwBefore=false
  override val providerId="simulator";override val flowVersion="sim-v1";override val submissionBoundary="test"
  override suspend fun readiness(job:Assignment)=emptyList<ReadinessCheck>()
  override suspend fun prepare(job:Assignment){if(throwBefore)throw IllegalStateException()}
  override suspend fun executeSubmission(job:Assignment):Evidence {submissions++;if(throwAfter)throw IllegalStateException();return Evidence(if(reject)ResultKind.NOT_PAID_CONFIRMED else ResultKind.SUCCESS_CONFIRMED,"TEST")}
  override fun interpret(job:Assignment,evidence:Evidence)=evidence
  override suspend fun captureEvidence(job:Assignment):Evidence?=null
  override suspend fun cancelBeforeSubmission(job:Assignment){}
  override suspend fun recover(job:Assignment):Evidence?=null
 }
 private fun engine(s:Store,b:Server,p:Provider)=WorkerEngine(s,b,p,Readiness{emptyList()},{config},TimeSource{1000})
 @Test fun successAndDuplicateDeliveryExecuteExactlyOnce()=runBlocking {
  val s=Store();val b=Server(job());val p=Provider();val e=engine(s,b,p);e.start();e.cycle();e.cycle()
  assertEquals(1,p.submissions);assertEquals(Phase.CONFIRMED_SUCCESS,s.a!!.phase)
 }
 @Test fun competingCallbacksCannotExecuteTwice()=runBlocking {
  val s=Store();val b=Server(job());val p=Provider();val e=engine(s,b,p);e.start()
  coroutineScope {repeat(20){launch{e.cycle()}}};assertEquals(1,p.submissions)
 }
 @Test fun storageFailureAtBoundaryPreventsSubmission()=runBlocking {
  val s=Store().apply{failBoundary=true};val p=Provider();val e=engine(s,Server(job()),p);e.start();e.cycle();assertEquals(0,p.submissions)
 }
 @Test fun networkFailureAfterSubmissionIsUnknownAndQuarantined()=runBlocking {
  val s=Store();val p=Provider().apply{throwAfter=true};val e=engine(s,Server(job()),p);e.start();e.cycle();e.cycle()
  assertEquals(Phase.UNKNOWN,s.a!!.phase);assertNotNull(s.q);assertEquals(1,p.submissions)
 }
 @Test fun networkFailureBeforeSubmissionIsNotPaid()=runBlocking {
  val s=Store();val p=Provider().apply{throwBefore=true};val e=engine(s,Server(job()),p);e.start();e.cycle()
  assertEquals(Phase.CONFIRMED_NOT_PAID,s.a!!.phase);assertEquals(0,p.submissions)
 }
 @Test fun expiredAuthorizationPreventsSubmission()=runBlocking {
  val s=Store();val p=Provider();val b=Server(job()).apply{expiry=999};val e=engine(s,b,p);e.start();e.cycle();assertEquals(0,p.submissions)
 }
 @Test fun revokedDeviceCannotClaim()=runBlocking {
  val s=Store();val p=Provider();val e=engine(s,Server(job()).apply{revoked=true},p);e.start()
  try{e.cycle();fail()}catch(_:WorkerFailure.Authentication){};assertEquals(0,p.submissions);assertNull(s.a)
 }
 @Test fun recoveryNeverResubmitsAtAnyUnfinishedPhase()=runBlocking {
  for(phase in Phase.entries.filter{!it.confirmed}) {
   val s=Store();s.a=Attempt(job(),phase,2,1,submissionAt=if(phase.uncertain)1 else null)
   val p=Provider();val e=engine(s,Server(job()),p);e.recover();e.start();e.cycle()
   assertEquals(0,p.submissions);assertEquals(Phase.RECONCILIATION_REQUIRED,s.a!!.phase);assertNotNull(s.q)
  }
 }
 @Test fun conflictingPayloadCannotExecute()=runBlocking {
  val s=Store();val p=Provider();val e=engine(s,Server(job().copy(amountMinor=2000)),p);e.start();e.cycle();assertEquals(0,p.submissions)
 }
 @Test fun impossibleTransitionsRejected() {assertFalse(Phase.UNKNOWN.permits(Phase.READY));assertFalse(Phase.SUBMISSION_POSSIBLE.permits(Phase.READY));assertFalse(Phase.CONFIRMED_SUCCESS.permits(Phase.PREPARING));assertFalse(Phase.RECEIVED.permits(Phase.CONFIRMED_SUCCESS))}
 @Test fun immutableHashAndExactAmountValidated() {job().validate(config,1000);assertNotEquals(job().payloadHash,job().copy(amountMinor=1001).immutableHash());try{job().copy(amountMinor=0).validate(config,1000);fail()}catch(_:IllegalArgumentException){}}
 @Test fun pauseAndDrainPreventClaims()=runBlocking {val s=Store();val p=Provider();val e=engine(s,Server(job()),p);e.cycle();e.start();e.drain();e.cycle();assertNull(s.a);assertEquals(0,p.submissions)}
}
