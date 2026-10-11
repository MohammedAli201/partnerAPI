package no.jubapay.payoutworker.data

import androidx.room.Room
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import kotlinx.coroutines.*
import no.jubapay.payoutworker.domain.*
import org.junit.*
import org.junit.Assert.*
import org.junit.runner.RunWith

/** Disk-backed real Room. Reopen simulates abrupt process loss at committed boundaries. */
@RunWith(AndroidJUnit4::class) class RoomRecoveryTest {
 private val context=ApplicationProvider.getApplicationContext<android.content.Context>()
 private val name="safety-test.db"
 private lateinit var db:WorkerDatabase
 private val cipher=KeystoreCipher()
 private fun open()=Room.databaseBuilder(context,WorkerDatabase::class.java,name).build()
 @Before fun setup(){context.deleteDatabase(name);db=open()}
 @After fun cleanup(){db.close();context.deleteDatabase(name)}
 private fun job(id:String="attempt"):Assignment {val a=Assignment("payout-$id",id,"device",1,"simulator","account",-1,"+252610000000","MSISDN",1000,"USD","","sim-v1",Long.MAX_VALUE,Long.MAX_VALUE,"correlation");return a.copy(payloadHash=a.immutableHash())}
 @Test fun moneyJsonRejectsFloatAndStringCoercion() {
  for(value in listOf<Any>(10.5,"1000")) {
   val j=Wire.assignment(job()).put("amount_minor",value)
   try { Wire.assignment(j);fail("Money coercion accepted") } catch(_:IllegalArgumentException){}
  }
 }
 @Test fun boundaryAndOutboxSurviveDatabaseReopen()=runBlocking {
  var store=RoomAttemptStore(db,cipher);val j=job();store.accept(j)
  store.transition(j.attemptId,Phase.RECEIVED,Phase.VALIDATED);store.transition(j.attemptId,Phase.VALIDATED,Phase.READY);store.transition(j.attemptId,Phase.READY,Phase.PREPARING)
  store.transition(j.attemptId,Phase.PREPARING,Phase.SUBMISSION_POSSIBLE,authorization=Authorization("auth",j.attemptId,j.payloadHash,Long.MAX_VALUE))
  db.close();db=open();store=RoomAttemptStore(db,cipher)
  assertEquals(Phase.SUBMISSION_POSSIBLE,store.get(j.attemptId)!!.phase);assertEquals("auth",store.get(j.attemptId)!!.authorizationId)
  assertEquals(listOf(1L,2L,3L,4L,5L),store.pending().map{it.sequence});assertFalse(store.hasCapacity())
  val id=store.pending().first().eventId;store.acknowledge(id);store.acknowledge(id);assertEquals(4,store.pending().size)
  assertFalse(db.dao().get(j.attemptId)!!.encryptedJob.contains(j.recipient))
 }
 @Test fun parallelAssignmentsEnforceOneActiveSlot()=runBlocking {
  val store=RoomAttemptStore(db,cipher)
  val results=coroutineScope{(1..12).map{async(Dispatchers.IO){runCatching{store.accept(job("a$it"))}.isSuccess}}.awaitAll()}
  assertEquals(1,results.count{it});assertEquals(1,store.all().size);assertEquals(1,store.pending().size)
 }
 @Test fun conflictingDuplicateDoesNotOverwriteEvidence()=runBlocking {
  val store=RoomAttemptStore(db,cipher);val j=job();store.accept(j);store.accept(j)
  try{store.accept(j.copy(recipient="+252610999999"));fail()}catch(_:WorkerFailure.Conflict){}
  assertEquals(j,store.get(j.attemptId)!!.assignment);assertEquals(1,store.pending().size)
 }
 @Test fun transactionRollsBackWhenEventEncryptionFails()=runBlocking {
  var calls=0;val failing=object:RecordCipher {override fun seal(value:String):String {calls++;if(calls==2)throw IllegalStateException("Injected outbox write failure");return cipher.seal(value)};override fun open(value:String)=cipher.open(value)}
  try{RoomAttemptStore(db,failing).accept(job());fail()}catch(_:IllegalStateException){}
  assertEquals(0,db.dao().count());assertEquals(0,db.dao().pendingCount());assertNull(db.dao().control())
 }
 @Test fun pinRateLimitAndVerifierSurviveNewInstances() {
  val prefs=context.getSharedPreferences("protected-settings",0);prefs.edit().clear().commit()
  val vault=Vault(context,cipher);val pin=OperatorPin(vault){1000L};pin.setup("482951","482951")
  repeat(5){assertFalse(pin.verify("111111"))}
  assertFalse(OperatorPin(vault){1001L}.verify("482951"));assertTrue(OperatorPin(vault){40_000L}.verify("482951"))
  assertFalse(prefs.getString("pin","")!!.contains("482951"));prefs.edit().clear().commit()
 }
}
