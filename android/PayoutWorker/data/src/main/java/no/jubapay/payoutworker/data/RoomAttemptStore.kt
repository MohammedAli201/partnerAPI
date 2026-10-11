package no.jubapay.payoutworker.data

import androidx.room.withTransaction
import kotlinx.coroutines.flow.map
import no.jubapay.payoutworker.domain.*
import org.json.JSONObject
import java.util.UUID

class RoomAttemptStore(private val db: WorkerDatabase,private val cipher: RecordCipher,
 private val time: TimeSource=TimeSource{System.currentTimeMillis()}): AttemptStore {
 private val dao=db.dao()
 override val changes=dao.observe().map { rows->rows.map(::decode) }
 private fun decode(r: AttemptRow)=Attempt(Wire.assignment(JSONObject(cipher.open(r.encryptedJob))),Phase.valueOf(r.phase),r.sequence,r.updatedAt,
  r.authorizationId,r.submissionAt,r.encryptedEvidence?.let{Wire.evidence(JSONObject(cipher.open(it)))},r.acknowledged)
 override suspend fun all()=dao.all().map(::decode)
 override suspend fun get(id: String)=dao.get(id)?.let(::decode)
 override suspend fun accept(job: Assignment): Attempt=db.withTransaction {
  dao.get(job.attemptId)?.let { if(it.payloadHash!=job.payloadHash || decode(it).assignment!=job) throw WorkerFailure.Conflict(); return@withTransaction decode(it) }
  if(dao.payout(job.payoutId)!=null) throw WorkerFailure.Conflict()
  val control=dao.control()?:ControlRow()
  if(control.activeAttempt!=null||control.quarantine!=null) throw WorkerFailure.Conflict()
  if(dao.count()>=1000||dao.pendingCount()>=1000) throw WorkerFailure.Capacity()
  val r=AttemptRow(job.attemptId,job.payoutId,job.payloadHash,cipher.seal(Wire.assignment(job).toString()),Phase.RECEIVED.name,1,time.now())
  dao.insert(r);dao.control(control.copy(activeAttempt=job.attemptId));append(r);decode(r)
 }
 override suspend fun transition(id: String,expected: Phase,next: Phase,evidence: Evidence?,authorization: Authorization?): Attempt=db.withTransaction {
  val old=dao.get(id)?:throw WorkerFailure.Conflict()
  check(old.phase==expected.name && expected.permits(next)) {"ILLEGAL_TRANSITION"}
  if(next==Phase.SUBMISSION_POSSIBLE) {
   check(old.authorizationId==null && authorization!=null && authorization.attemptId==id && authorization.payloadHash==old.payloadHash && authorization.expiresAt>time.now()) {"INVALID_OR_CONSUMED_AUTHORIZATION"}
  } else check(authorization==null)
  if(next.confirmed) check(evidence?.kind == if(next==Phase.CONFIRMED_SUCCESS) ResultKind.SUCCESS_CONFIRMED else ResultKind.NOT_PAID_CONFIRMED)
  if(dao.pendingCount()>=2000) throw WorkerFailure.Capacity()
  val r=old.copy(phase=next.name,sequence=old.sequence+1,updatedAt=time.now(),authorizationId=authorization?.id?:old.authorizationId,
   submissionAt=if(next==Phase.SUBMISSION_POSSIBLE)time.now()else old.submissionAt,
   encryptedEvidence=evidence?.let{cipher.seal(Wire.evidence(it).toString())}?:old.encryptedEvidence)
  dao.update(r);append(r);decode(r)
 }
 private suspend fun append(r: AttemptRow) {
  val a=decode(r);val e=Event(UUID.randomUUID().toString(),r.payoutId,r.id,a.assignment.assignmentVersion,r.sequence,a.phase,r.updatedAt,r.payloadHash,a.evidence)
  dao.event(OutboxRow(e.eventId,r.id,r.sequence,cipher.seal(Wire.event(e).toString())))
 }
 override suspend fun pending()=dao.events().map{Wire.event(JSONObject(cipher.open(it.encryptedEvent)))}
 override suspend fun acknowledge(eventId: String)=db.withTransaction {
  val e=dao.event(eventId)?:return@withTransaction
  val a=dao.get(e.attemptId)?:throw WorkerFailure.Conflict()
  if(Phase.valueOf(a.phase).confirmed && e.sequence==a.sequence) {
   dao.update(a.copy(acknowledged=true));val c=dao.control()?:ControlRow()
   if(c.activeAttempt==a.id)dao.control(c.copy(activeAttempt=null))
  }
  dao.deleteEvent(eventId)
 }
 override suspend fun quarantine(reason: String)=db.withTransaction {dao.control((dao.control()?:ControlRow()).copy(quarantine=reason))}
 override suspend fun quarantineReason()=dao.control()?.quarantine
 override suspend fun clearQuarantineAfterReconciliation()=db.withTransaction {
  val c=dao.control()?:return@withTransaction
  if(c.quarantine in setOf("UNFINISHED_ATTEMPT","UNRESOLVED_SUBMISSION") && dao.all().all {Phase.valueOf(it.phase).confirmed&&it.acknowledged}) dao.control(c.copy(quarantine=null))
 }
 override suspend fun hasCapacity(): Boolean=dao.count()<1000 && dao.pendingCount()<1000 && dao.control()?.activeAttempt==null && dao.control()?.quarantine==null
}
