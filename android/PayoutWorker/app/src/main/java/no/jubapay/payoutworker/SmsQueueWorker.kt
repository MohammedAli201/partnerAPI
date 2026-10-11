package no.jubapay.payoutworker

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.net.Uri
import android.telephony.SmsManager
import android.telephony.SubscriptionManager
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import no.jubapay.payoutworker.data.*
import org.json.JSONObject

/** Real modem calls. A durable local send fence plus backend slot prevents replay. */
class SmsQueueWorker(private val context:Context,private val backend:HttpBackend,private val vault:Vault) {
 val running=MutableStateFlow(false)
 val status=MutableStateFlow("SMS queue stopped")
 val history=MutableStateFlow<List<String>>(emptyList())
 private val execution=Mutex()
 private val uploads=Mutex()
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
 @Volatile private var stopped=false
 private fun records()=JSONObject(vault.get("sms-records")?:"{}")
 @Synchronized private fun read(id:String)=records().optJSONObject(id)
 @Synchronized private fun save(id:String,update:(JSONObject)->Unit) {
  val all=records();val item=all.optJSONObject(id)?:JSONObject();update(item);all.put(id,item)
  vault.put("sms-records",all.toString())
  history.value=all.keys().asSequence().map {key->all.getJSONObject(key)}.sortedBy{it.getJSONObject("job").getInt("ordinal")}
   .map {"${it.getJSONObject("job").getString("message")}: ${it.getString("status")}${if(it.optBoolean("reported"))" (saved in Hubaal)"else" (report pending)"}${it.optString("delivery").takeIf{d->d.isNotBlank()}?.let{d->" / $d"}?:""}"}.toList()
 }
 fun enabled()=vault.get("sms-worker-enabled")=="true"
 fun enable(){vault.put("sms-worker-enabled","true")}
 fun stop(){vault.put("sms-worker-enabled","false");stopped=true;status.value="Stopping after current send result"}
 suspend fun flush()=uploads.withLock {
  val all=synchronized(this){records()}
  for(id in all.keys()) {
   val item=read(id)?:continue
   if(item.getString("status") in setOf("SENT","FAILED","UNKNOWN")&&!item.optBoolean("reported")) {
    backend.smsResult(item.getJSONObject("job"),item.getString("status"),if(item.isNull("code"))null else item.getInt("code"),item.getString("detail"))
    save(id){it.put("reported",true)}
   }
   if(item.optString("delivery").isNotBlank()&&!item.optBoolean("delivery_reported")) {
    backend.smsDelivery(item.getJSONObject("job"),item.getString("delivery"))
    save(id){it.put("delivery_reported",true)}
   }
  }
 }
 fun callback(id:String,kind:String,code:Int) {
  val old=read(id)?:return
  if(kind=="sent"&&old.optString("status") in setOf("SENDING","UNKNOWN")) {
   save(id){it.put("status",if(code==Activity.RESULT_OK)"SENT"else"FAILED").put("code",code)
    .put("detail","Android SMS sent callback: $code").put("reported",false)}
  } else if(kind=="delivery") {
   save(id){it.put("delivery",if(code==Activity.RESULT_OK)"DELIVERED"else"DELIVERY_FAILED").put("delivery_reported",false)}
  }
  scope.launch {try{flush()}catch(_:Exception){status.value="SMS result saved locally; backend reporting pending"}}
 }
 private fun pending(id:String,kind:String):PendingIntent {
  val intent=Intent(context,SmsResultReceiver::class.java).setData(Uri.parse("payoutworker://sms/$id/$kind"))
   .putExtra("job_id",id).putExtra("kind",kind)
  return PendingIntent.getBroadcast(context,0,intent,PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
 }
 suspend fun run()=execution.withLock {
  check(context.checkSelfPermission(Manifest.permission.SEND_SMS)==PackageManager.PERMISSION_GRANTED){"SMS permission required"}
  val subscription=SubscriptionManager.getDefaultSmsSubscriptionId()
  check(SubscriptionManager.isValidSubscriptionId(subscription)){"Select a default SMS SIM in Android settings"}
  @Suppress("DEPRECATION") val manager=SmsManager.getSmsManagerForSubscriptionId(subscription)
  stopped=false;running.value=true
  try {
   run {
    while(!stopped && enabled()) {
     flush()
     val reply=backend.smsClaim()
     if(reply.optJSONObject("blocked")!=null){status.value="Queue held: previous send is uncertain or awaiting result";delay(5_000);continue}
     val job=reply.optJSONObject("job")
     if(job==null){status.value="Automatic worker ready: waiting for the next backend job";delay(3_000);continue}
     val id=job.getString("job_id")
     val prior=read(id)
     if(prior!=null) {
      if(prior.optString("status") !in setOf("SENT","FAILED","UNKNOWN"))save(id){it.put("status","UNKNOWN").put("code",JSONObject.NULL).put("detail","Interrupted send; never automatically repeat")}
      flush();status.value="Recovered previous job; queue held for review";break
     }
     // Authenticated backend supplies either numbered diagnostics or a payment-linked SMS substitute.
     val numbered=job.optString("kind")=="NUMBERED_TEST" && job.getString("recipient")=="97368681" && job.getString("message")=="Message ${job.getInt("ordinal")}" && job.getInt("ordinal") in 1..10
     val payment=job.optString("kind")=="SMS_PAYOUT_TEST" && runCatching{java.util.UUID.fromString(job.getString("payout_id"))}.isSuccess && job.getString("message").startsWith("SMS TEST ")
     check((numbered||payment) && job.getString("recipient").matches(Regex("\\+?[0-9]{7,15}")) && job.getString("message").length<=160){"Unexpected SMS test instruction"}
     save(id){it.put("job",job).put("status","PREPARED").put("code",JSONObject.NULL).put("detail","")}
     status.value="${job.getString("message")}: requesting exclusive send authorization"
     val permit=backend.smsStart(job,subscription)
     if(!permit.getBoolean("can_send")){status.value="Send authorization already consumed; no retry";break}
     save(id){it.put("status","SENDING").put("subscription_id",subscription)}
     status.value="${job.getString("message")}: sending on SMS SIM $subscription; other jobs wait"
     try {manager.sendTextMessage(job.getString("recipient"),null,job.getString("message"),pending(id,"sent"),pending(id,"delivery"))}
     catch(_:Exception){save(id){it.put("status","UNKNOWN").put("detail","Modem call interrupted; no automatic retry")}}
     withTimeoutOrNull(90_000){while(read(id)?.optString("status")=="SENDING")delay(250)}
     if(read(id)?.optString("status")=="SENDING")save(id){it.put("status","UNKNOWN").put("detail","No Android sent callback within 90 seconds; queue held")}
     flush()
     if(read(id)?.getString("status")=="UNKNOWN"){status.value="Unknown send result; remaining jobs held";delay(5_000);continue}
     status.value="${job.getString("message")}: result saved; requesting next job"
    }
   }
  } catch(_:Exception){status.value="Session stopped; retain current job and reports. No automatic resend."}
  finally {running.value=false}
 }
}

class SmsResultReceiver:BroadcastReceiver() {
 override fun onReceive(context:Context,intent:Intent) {
  val id=intent.getStringExtra("job_id")?:return
  val kind=intent.getStringExtra("kind")?:return
  (context.applicationContext as WorkerApplication).graph.sms.callback(id,kind,resultCode)
 }
}
