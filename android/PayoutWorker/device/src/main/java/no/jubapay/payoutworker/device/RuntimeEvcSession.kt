package no.jubapay.payoutworker.device

import android.Manifest
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.telecom.PhoneAccountHandle
import android.telecom.TelecomManager
import android.telephony.SubscriptionManager
import android.telephony.TelephonyManager
import android.view.accessibility.AccessibilityNodeInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import no.jubapay.payoutworker.domain.*
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

/** Inspect the actual native phone dialog, not coordinates or guessed Samsung view IDs.
 * Only OS-installed telephony packages are eligible. PIN fields are never read.
 */
object RuntimeEvcSession:InteractiveUssdSession {
 private val parser=Evc712Parser()
 private val nativePackages=setOf("com.android.phone","com.samsung.android.incallui","com.samsung.android.dialer","com.android.server.telecom","com.samsung.android.app.telephonyui")
 private data class Profile(val fingerprint:String,val pkg:String,val signer:String,val prompt:String,val reply:String,val send:String,val cancel:String)
 private data class Active(val token:String,val job:Assignment,var profile:Profile?=null,val submitted:AtomicBoolean=AtomicBoolean(false))
 @Volatile private var active:Active?=null
 private val screens=MutableSharedFlow<UssdScreen>(replay=1,extraBufferCapacity=8)
 private fun service()=EvcAccessibilityService.instance?:error("ACCESSIBILITY_UNAVAILABLE")

 fun subscription(context:Context):Int {
  check(context.checkSelfPermission(Manifest.permission.READ_PHONE_STATE)==PackageManager.PERMISSION_GRANTED){"SIM_PERMISSION_REQUIRED"}
  val sims=context.getSystemService(SubscriptionManager::class.java).activeSubscriptionInfoList.orEmpty().filter {
   val tm=context.getSystemService(TelephonyManager::class.java).createForSubscriptionId(it.subscriptionId)
   tm.simOperatorName.contains("hormuud",true)||it.carrierName.toString().contains("hormuud",true)
  }
  check(sims.isNotEmpty()){ "HORMUUD_SIM_REQUIRED" }
  val default=SubscriptionManager.getDefaultVoiceSubscriptionId()
  return sims.singleOrNull()?.subscriptionId ?: sims.singleOrNull{it.subscriptionId==default}?.subscriptionId ?: error("SELECT_HORMUUD_DEFAULT_CALL_SIM")
 }
 fun setupChecks(context:Context)=listOf(
  ReadinessCheck("EVC accessibility",EvcAccessibilityService.instance!=null,"Enable PayoutWorker EVC integration"),
  ReadinessCheck("Phone permission",context.checkSelfPermission(Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED,"Allow Phone permission"),
  ReadinessCheck("Hormuud SIM",runCatching{subscription(context)>=0}.getOrDefault(false),"Allow SIM details; use a Hormuud SIM"),
  ReadinessCheck("Unlocked screen",!context.getSystemService(KeyguardManager::class.java).isKeyguardLocked,"Keep this dedicated worker phone unlocked"),
  ReadinessCheck("Android USSD support",Build.VERSION.SDK_INT>=30,"Android 11 or later for exact SIM routing"))
 private fun phoneAccount(context:Context,sub:Int):PhoneAccountHandle? {
  if(Build.VERSION.SDK_INT<30)return null
  return context.getSystemService(TelecomManager::class.java).callCapablePhoneAccounts.singleOrNull {
   context.getSystemService(TelephonyManager::class.java).createForPhoneAccountHandle(it)?.subscriptionId==sub
  }
 }
 override suspend fun readiness(job:Assignment)=withContext(Dispatchers.Main) {
  val context=service()
  setupChecks(context)+ReadinessCheck("Assigned EVC SIM",runCatching{subscription(context)==job.simSubscriptionId&&phoneAccount(context,job.simSubscriptionId)!=null}.getOrDefault(false),"Exact backend assignment and phone account match")
 }
 private fun signature(context:Context,pkg:String):String? {
  if(pkg !in nativePackages)return null
  val info=context.packageManager.getPackageInfo(pkg,PackageManager.GET_SIGNING_CERTIFICATES)
  val flags=info.applicationInfo?.flags?:return null
  if(flags.and(ApplicationInfo.FLAG_SYSTEM or ApplicationInfo.FLAG_UPDATED_SYSTEM_APP)==0)return null
  val signer=info.signingInfo?.apkContentsSigners?.singleOrNull()?:return null
  return MessageDigest.getInstance("SHA-256").digest(signer.toByteArray()).joinToString(""){"%02x".format(it)}
 }
 private fun nodes(root:AccessibilityNodeInfo):List<AccessibilityNodeInfo> {
  val result=mutableListOf<AccessibilityNodeInfo>()
  fun walk(node:AccessibilityNodeInfo,depth:Int) {
   if(depth>30||result.size>=512)return
   if(node.isVisibleToUser)result.add(node)
   for(i in 0 until node.childCount)node.getChild(i)?.let{walk(it,depth+1)}
  }
  walk(root,0);return result
 }
 private fun unique(root:AccessibilityNodeInfo,id:String)=root.findAccessibilityNodeInfosByViewId(id).filter{it.isVisibleToUser}.singleOrNull()
 private fun discover(context:Context,a:Active,root:AccessibilityNodeInfo):Profile? {
  val pkg=root.packageName?.toString()?:return null
  val signer=signature(context,pkg)?:return null
  val all=nodes(root)
  val prompt=all.filter{!it.isEditable&&!it.isPassword&&!it.isClickable&&it.viewIdResourceName!=null}
   .singleOrNull{parser.verifyPrompt(a.job,it.text?.toString().orEmpty())!=Evc712Parser.Prompt.UNRECOGNIZED}?:return null
  val reply=all.singleOrNull{it.isEditable&&it.isEnabled&&it.viewIdResourceName!=null}?:return null
  fun button(label:String)=all.singleOrNull{!it.isEditable&&!it.isPassword&&it.isClickable&&it.isEnabled&&it.viewIdResourceName!=null&&it.text?.toString()?.trim()?.equals(label,true)==true}
  val send=button("Send")?:return null;val cancel=button("Cancel")?:return null
  return Profile(Build.FINGERPRINT,pkg,signer,prompt.viewIdResourceName,reply.viewIdResourceName,send.viewIdResourceName,cancel.viewIdResourceName)
 }
 private fun snapshot(context:Context,a:Active):UssdScreen? {
  val root=service().rootInActiveWindow?:return null
  val p=a.profile?:discover(context,a,root)?.also{a.profile=it}?:return null
  if(p.fingerprint!=Build.FINGERPRINT||root.packageName?.toString()!=p.pkg||signature(context,p.pkg)!=p.signer)return null
  val display=unique(root,p.prompt)?:return null
  if(display.isEditable||display.isPassword)return null
  val text=display.text?.toString()?.takeIf{it.length<=4096}?:return null
  val reply=unique(root,p.reply);val send=unique(root,p.send)
  return UssdScreen(a.token,root.windowId,text,reply?.isEditable==true&&reply.isEnabled&&send?.isClickable==true&&send.isEnabled)
 }
 fun onEvent(context:Context) {
  val current=active?:return
  runCatching{snapshot(context,current)?.let{screens.tryEmit(it)}}
 }
 fun disconnected(){active?.let{screens.tryEmit(UssdScreen(it.token,-1,"Session lost",false))}}
 override suspend fun open(job:Assignment,command:String):UssdScreen {
  parser.validate(job);check(command==parser.command(job))
  val token=UUID.randomUUID().toString();check(UssdDeviceLease.acquire(token)){"USSD_BUSY"}
  try {
   withContext(Dispatchers.Main) {
    val s=service();check(active==null&&setupChecks(s).all{it.ready})
    val account=phoneAccount(s,job.simSubscriptionId)?:error("SIM_NOT_VERIFIED")
    val old=s.rootInActiveWindow
    check(old==null||old.packageName?.toString() !in nativePackages||nodes(old).none{it.isEditable&&it.isVisibleToUser}) {"EXISTING_PHONE_INPUT_DIALOG"}
    active=Active(token,job)
    s.startActivity(Intent(Intent.ACTION_CALL,Uri.fromParts("tel",command,null)).putExtra(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE,account).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
   }
   return withTimeout(45_000){screens.first{it.session==token}}
  }catch(e:Exception){release(token);throw e}
 }
 override suspend fun current(session:String)=withContext(Dispatchers.Main) {
  val a=active?:error("SESSION_LOST");check(a.token==session);snapshot(service(),a)?:error("DIALOGUE_LOST")
 }
 override suspend fun submitPin(job:Assignment,screen:UssdScreen,pin:CharArray):String {
  withContext(Dispatchers.Main) {
   val a=active?:error("SESSION_LOST");check(a.job==job&&a.token==screen.session)
   val fresh=snapshot(service(),a)?:error("DIALOGUE_LOST")
   check(fresh.windowId==screen.windowId&&fresh.canReply&&parser.verifyPrompt(job,fresh.text)==Evc712Parser.Prompt.MATCH)
   check(a.submitted.compareAndSet(false,true)){"PIN_ALREADY_ATTEMPTED"}
   val p=a.profile?:error("PROFILE_LOST");val root=service().rootInActiveWindow?:error("DIALOGUE_LOST")
   val reply=unique(root,p.reply)?:error("AMBIGUOUS_REPLY")
   val args=Bundle().apply{putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,String(pin))}
   check(reply.isEditable&&reply.isEnabled&&reply.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,args)){"SET_TEXT_FAILED"}
   val after=snapshot(service(),a)?:error("DIALOGUE_LOST")
   check(after.windowId==screen.windowId&&after.canReply&&parser.verifyPrompt(job,after.text)==Evc712Parser.Prompt.MATCH)
   val send=unique(service().rootInActiveWindow?:error("DIALOGUE_LOST"),p.send)?:error("AMBIGUOUS_SEND")
   check(send.isEnabled&&send.isClickable&&send.text?.toString()?.trim()?.equals("Send",true)==true&&send.performAction(AccessibilityNodeInfo.ACTION_CLICK)){"SEND_FAILED"}
  }
  return withTimeout(45_000){screens.first{it.session==screen.session&&!it.canReply&&it.text!=screen.text}.text}
 }
 override suspend fun closeBeforeSubmission(session:String)=withContext(Dispatchers.Main) {
  val a=active?:return@withContext
  if(a.token!=session||a.submitted.get())return@withContext
  val p=a.profile?:return@withContext;val root=service().rootInActiveWindow?:return@withContext
  if(root.packageName?.toString()==p.pkg)unique(root,p.cancel)?.takeIf{it.isEnabled&&it.isClickable&&it.text?.toString()?.trim()?.equals("Cancel",true)==true}?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
 }
 override fun release(session:String){if(active?.token==session)active=null;UssdDeviceLease.release(session)}
}
