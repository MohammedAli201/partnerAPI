package no.jubapay.payoutworker.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.sync.Mutex
import kotlinx.coroutines.sync.withLock
import no.jubapay.payoutworker.domain.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.HttpUrl.Companion.toHttpUrl
import org.json.JSONObject
import java.util.concurrent.TimeUnit

class HttpBackend(private val vault: Vault, private val key: DeviceKey,private val debug: Boolean): Backend {
 private val renewal=Mutex()
 private val client=OkHttpClient.Builder().connectTimeout(10,TimeUnit.SECONDS).readTimeout(35,TimeUnit.SECONDS).callTimeout(40,TimeUnit.SECONDS)
  .followRedirects(false).followSslRedirects(false).retryOnConnectionFailure(false).build()
 fun enrolled()=vault.get("credentials")!=null
 fun config(): DeviceConfig=Wire.config(JSONObject(vault.get("credentials")?:throw WorkerFailure.Authentication()).getJSONObject("config"))
 fun baseUrl()=vault.get("backend")?:""
 private fun checkedUrl(raw: String): String {
  val u=raw.toHttpUrl(); require(u.username.isEmpty()&&u.password.isEmpty()&&u.query==null&&u.fragment==null&&u.encodedPath=="/") {"INVALID_BACKEND_URL"}
  val local=u.host=="localhost" || u.host=="10.0.2.2" || u.host.matches(Regex("127\\.[0-9.]+|10\\.[0-9.]+|192\\.168\\.[0-9.]+|172\\.(1[6-9]|2[0-9]|3[01])\\.[0-9.]+"))
  require(u.isHttps || (debug&&local&&u.scheme=="http")) {"HTTPS_REQUIRED"};return u.toString().trimEnd('/')
 }
 suspend fun enroll(url: String,code: String) {
  require(!enrolled()) {"ALREADY_ENROLLED"}
  val base=checkedUrl(url)
  val result=request(base,"/v1/enroll",JSONObject().put("code",code).put("public_key",key.publicKey()).put("signature",key.sign("enroll:$code")),null)
  check(Wire.config(result.getJSONObject("config")).simulation) {"REAL_EXECUTION_DISABLED"}
  vault.put("backend",base);vault.put("credentials",result.toString())
 }
 private suspend fun credentials(): JSONObject=renewal.withLock {
  var c=JSONObject(vault.get("credentials")?:throw WorkerFailure.Authentication())
  if(c.getLong("expires_at")<System.currentTimeMillis()+60_000) {
   val refresh=c.getString("refresh_token")
   c=request(checkedUrl(baseUrl()),"/v1/renew",JSONObject().put("device_id",c.getJSONObject("config").getString("device_id"))
    .put("refresh_token",refresh).put("signature",key.sign("renew:$refresh")),null)
   vault.put("credentials",c.toString())
  };c
 }
 private suspend fun call(path: String,body: JSONObject=JSONObject()): JSONObject {val c=credentials();return request(checkedUrl(baseUrl()),path,body,c.getString("access_token"))}
 private suspend fun request(base: String,path: String,body: JSONObject,token: String?): JSONObject=withContext(Dispatchers.IO) {
  val b=Request.Builder().url(base+path).post(body.toString().toRequestBody("application/json".toMediaType()))
  if(token!=null)b.header("Authorization","Bearer $token")
  client.newCall(b.build()).execute().use { response ->
   if(response.code==401||response.code==403)throw WorkerFailure.Authentication()
   if(response.code==409)throw WorkerFailure.Conflict()
   if(!response.isSuccessful)throw WorkerFailure.Protocol("HTTP_${response.code}")
   val source=response.body?.source()?:throw WorkerFailure.Protocol("EMPTY_RESPONSE")
   if(source.request(256*1024L+1))throw WorkerFailure.Protocol("RESPONSE_TOO_LARGE")
   JSONObject(source.readUtf8())
  }
 }
 override suspend fun heartbeat(state: DeviceState): Control {val j=call("/v1/heartbeat",JSONObject().put("state",state.name).put("app_version","1.0").put("flow_version","sim-v1"));return Control(j.getBoolean("paused"),j.getBoolean("drain"),j.getBoolean("revoked"))}
 override suspend fun claim(): Assignment?=call("/v1/claim",JSONObject().put("wait_seconds",20)).optJSONObject("assignment")?.let(Wire::assignment)
 override suspend fun acknowledgeAssignment(job: Assignment) {call("/v1/assignment/ack",binding(job))}
 override suspend fun authorize(job: Assignment): Authorization {val j=call("/v1/authorize",binding(job));return Authorization(j.getString("authorization_id"),j.getString("attempt_id"),j.getString("payload_hash"),j.getLong("expires_at"))}
 override suspend fun upload(event: Event)=call("/v1/events",Wire.event(event)).optString("ack_event_id")==event.eventId
 override suspend fun reconcile(attempt: Attempt): Reconciliation {val j=call("/v1/reconcile",binding(attempt.assignment));return Reconciliation(j.getBoolean("resolved"),j.optJSONObject("evidence")?.let(Wire::evidence),j.optString("audit_id").ifBlank{null})}
 suspend fun standaloneUssdInstruction(requestId: String,recipient: String): JSONObject=call("/v1/ussd-tests/standalone",JSONObject().put("request_id",requestId).put("recipient",recipient))
 suspend fun smsClaim(): JSONObject=call("/v1/sms/claim",JSONObject().put("worker_version",2))
 suspend fun smsStart(job:JSONObject,subscription:Int):JSONObject=call("/v1/sms/start",smsBinding(job).put("subscription_id",subscription))
 suspend fun smsResult(job:JSONObject,status:String,code:Int?,detail:String) {
  call("/v1/sms/result",smsBinding(job).put("status",status).put("result_code",code?:JSONObject.NULL).put("detail",detail))
 }
 suspend fun smsDelivery(job:JSONObject,delivery:String) {call("/v1/sms/delivery",smsBinding(job).put("delivery",delivery))}
 private fun smsBinding(job:JSONObject)=JSONObject().put("job_id",job.getString("job_id")).put("lease_id",job.getString("lease_id"))
 suspend fun manualUssdResult(testId: String,status: String,response: String?) {
  call("/v1/ussd-tests/result",JSONObject().put("test_id",testId).put("status",status).put("response",response?:JSONObject.NULL))
 }
 private fun binding(a: Assignment)=JSONObject().put("attempt_id",a.attemptId).put("payload_hash",a.payloadHash).put("assignment_version",a.assignmentVersion)
}
