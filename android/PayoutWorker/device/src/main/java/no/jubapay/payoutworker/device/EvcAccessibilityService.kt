package no.jubapay.payoutworker.device

import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.telecom.TelecomManager
import android.telephony.TelephonyManager
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.withContext
import kotlinx.coroutines.withTimeout
import no.jubapay.payoutworker.domain.*
import java.security.MessageDigest
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean
import java.util.concurrent.atomic.AtomicReference

/** Must be populated from an inspected Android build, never from iPhone coordinates or remote commands. */
data class VerifiedUssdProfile(
    val buildFingerprint:String,
    val packageName:String,
    val signingCertificateSha256:String,
    val promptViewId:String,
    val replyViewId:String,
    val sendViewId:String,
    val cancelViewId:String,
    val resultViewId:String,
    val phoneAccountId:String,
    val phoneAccountComponent:String,
    val openingRequestCannotTransfer:Boolean
)

/** Shared by the diagnostic and interactive adapters. Process death never resumes an active session. */
object UssdDeviceLease {
    private val owner=AtomicReference<String?>(null)
    fun acquire(id:String)=owner.compareAndSet(null,id)
    fun release(id:String){owner.compareAndSet(id,null)}
}

class EvcAccessibilityService:AccessibilityService() {
    private data class Active(val token:String,val job:Assignment,val profile:VerifiedUssdProfile,
        val submitted:AtomicBoolean=AtomicBoolean(false))
    private var active:Active?=null
    private val screens=MutableSharedFlow<UssdScreen>(replay=1,extraBufferCapacity=1,onBufferOverflow=BufferOverflow.DROP_OLDEST)
    private val parser=Evc712Parser()

    override fun onServiceConnected(){instance=this}
    override fun onDestroy(){RuntimeEvcSession.disconnected();active?.let{UssdDeviceLease.release(it.token)};active=null;instance=null;super.onDestroy()}
    override fun onInterrupt(){RuntimeEvcSession.disconnected();active?.let{screens.tryEmit(UssdScreen(it.token,-1,"",false))}}
    override fun onAccessibilityEvent(event:AccessibilityEvent?) {
        RuntimeEvcSession.onEvent(this)
        val current=active?:return
        // Do not inspect event.text: it can contain the provider PIN after ACTION_SET_TEXT.
        val snapshot=snapshot(current) ?: if(current.submitted.get())UssdScreen(current.token,-1,"",false) else return
        screens.tryEmit(snapshot)
    }

    private fun unique(root:AccessibilityNodeInfo,id:String):AccessibilityNodeInfo? =
        root.findAccessibilityNodeInfosByViewId(id).filter{it.isVisibleToUser}.singleOrNull()

    private fun snapshot(a:Active):UssdScreen? {
        val root=rootInActiveWindow?:return null
        if(root.packageName?.toString()!=a.profile.packageName)return null
        val prompt=unique(root,a.profile.promptViewId)
        val result=unique(root,a.profile.resultViewId)
        val reply=unique(root,a.profile.replyViewId)
        val send=unique(root,a.profile.sendViewId)
        val node=if(a.submitted.get())result?:prompt else prompt
        // Only the configured display node, never an input/password node or whole-screen dump.
        if(node==null || node.isEditable || node.isPassword)return null
        val text=node.text?.toString()?.takeIf{it.length<=4096}?:return null
        return UssdScreen(a.token,root.windowId,text,reply?.isEditable==true && reply.isEnabled && send?.isClickable==true && send.isEnabled)
    }

    private fun profileReady(profile:VerifiedUssdProfile):Boolean {
        if(Build.VERSION.SDK_INT<30 || profile.buildFingerprint!=Build.FINGERPRINT || !profile.openingRequestCannotTransfer)return false
        val ids=listOf(profile.promptViewId,profile.replyViewId,profile.sendViewId,profile.cancelViewId,profile.resultViewId)
        if(ids.any{!it.startsWith(profile.packageName+":id/")} || profile.signingCertificateSha256.length!=64)return false
        return try {
            val info=packageManager.getPackageInfo(profile.packageName,PackageManager.GET_SIGNING_CERTIFICATES)
            info.signingInfo?.apkContentsSigners?.any { signature ->
                MessageDigest.getInstance("SHA-256").digest(signature.toByteArray()).joinToString(""){"%02x".format(it)}==profile.signingCertificateSha256
            }==true
        }catch(_:Exception){false}
    }

    private fun phoneAccount(job:Assignment,p:VerifiedUssdProfile):android.telecom.PhoneAccountHandle? {
        if(Build.VERSION.SDK_INT<30 || checkSelfPermission(Manifest.permission.READ_PHONE_STATE)!=PackageManager.PERMISSION_GRANTED)return null
        return getSystemService(TelecomManager::class.java).callCapablePhoneAccounts.singleOrNull { handle ->
            handle.id==p.phoneAccountId && handle.componentName.flattenToString()==p.phoneAccountComponent &&
                getSystemService(TelephonyManager::class.java).createForPhoneAccountHandle(handle)?.subscriptionId==job.simSubscriptionId
        }
    }

    suspend fun ready(job:Assignment,p:VerifiedUssdProfile)=withContext(Dispatchers.Main) {
        listOf(ReadinessCheck("Verified Android USSD profile",profileReady(p),"Exact OS build, package signature and view IDs required"),
            ReadinessCheck("Call permission",checkSelfPermission(Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED,"Operator grants phone permission"),
            ReadinessCheck("Assigned SIM",runCatching{phoneAccount(job,p)!=null}.getOrDefault(false),"Exact phone account/subscription match required"))
    }

    suspend fun open(job:Assignment,command:String,p:VerifiedUssdProfile):UssdScreen {
        val token=UUID.randomUUID().toString()
        check(UssdDeviceLease.acquire(token)){"USSD_BUSY"}
        try {
            withContext(Dispatchers.Main) {
                check(active==null && profileReady(p) && command==parser.command(job))
                check(checkSelfPermission(Manifest.permission.CALL_PHONE)==PackageManager.PERMISSION_GRANTED)
                val account=phoneAccount(job,p)?:error("SIM_NOT_VERIFIED")
                val root=rootInActiveWindow
                check(root==null || root.packageName?.toString()!=p.packageName || unique(root,p.replyViewId)==null){"EXISTING_USSD_DIALOGUE"}
                active=Active(token,job,p)
                startActivity(Intent(Intent.ACTION_CALL,Uri.fromParts("tel",command,null))
                    .putExtra(TelecomManager.EXTRA_PHONE_ACCOUNT_HANDLE,account).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }
            return withTimeout(45_000){screens.first{it.session==token}}
        }catch(e:Exception){release(token);throw e}
    }

    suspend fun current(token:String)=withContext(Dispatchers.Main) {
        val a=active?:error("SESSION_LOST");check(a.token==token)
        snapshot(a)?:error("DIALOGUE_LOST")
    }

    suspend fun submit(job:Assignment,screen:UssdScreen,pin:CharArray):String {
        withContext(Dispatchers.Main) {
            val a=active?:error("SESSION_LOST")
            check(a.token==screen.session && a.job==job && profileReady(a.profile))
            val fresh=snapshot(a)?:error("DIALOGUE_LOST")
            check(fresh.windowId==screen.windowId && fresh.canReply && parser.verifyPrompt(job,fresh.text)==Evc712Parser.Prompt.MATCH)
            check(a.submitted.compareAndSet(false,true)){"PIN_ALREADY_ATTEMPTED"}
            val root=rootInActiveWindow?:error("DIALOGUE_LOST")
            val reply=unique(root,a.profile.replyViewId)?:error("AMBIGUOUS_REPLY")
            // Android requires CharSequence here; it remains only in transient framework memory.
            val arguments=Bundle().apply{putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,String(pin))}
            check(reply.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,arguments)){"SET_TEXT_FAILED"}
            val after=rootInActiveWindow?:error("DIALOGUE_LOST")
            check(after.windowId==screen.windowId && after.packageName?.toString()==a.profile.packageName)
            val prompt=unique(after,a.profile.promptViewId)?:error("PROMPT_LOST")
            check(!prompt.isEditable && !prompt.isPassword && parser.verifyPrompt(job,prompt.text?.toString().orEmpty())==Evc712Parser.Prompt.MATCH)
            val send=unique(after,a.profile.sendViewId)?:error("AMBIGUOUS_SEND")
            check(send.isEnabled && send.isClickable && send.performAction(AccessibilityNodeInfo.ACTION_CLICK)){"SEND_FAILED"}
        }
        return withTimeout(45_000){screens.first{it.session==screen.session && it.text!=screen.text}.text}
    }

    suspend fun cancel(token:String)=withContext(Dispatchers.Main) {
        val a=active?:return@withContext
        if(a.token!=token || a.submitted.get())return@withContext
        val root=rootInActiveWindow?:return@withContext
        if(root.packageName?.toString()==a.profile.packageName)unique(root,a.profile.cancelViewId)?.takeIf{it.isEnabled&&it.isClickable}?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }
    fun release(token:String){if(active?.token==token)active=null;UssdDeviceLease.release(token)}
    companion object {@Volatile var instance:EvcAccessibilityService?=null;private set}
}

/** No default profile is shipped: an unverified device cannot dial or enter a PIN. */
class AndroidInteractiveUssd(private val profile:VerifiedUssdProfile):InteractiveUssdSession {
    private fun service()=EvcAccessibilityService.instance?:error("ACCESSIBILITY_UNAVAILABLE")
    override suspend fun readiness(job:Assignment)=EvcAccessibilityService.instance?.ready(job,profile)
        ?:listOf(ReadinessCheck("Accessibility",false,"EVC service not connected"))
    override suspend fun open(job:Assignment,command:String)=service().open(job,command,profile)
    override suspend fun current(session:String)=service().current(session)
    override suspend fun submitPin(job:Assignment,screen:UssdScreen,pin:CharArray)=service().submit(job,screen,pin)
    override suspend fun closeBeforeSubmission(session:String){service().cancel(session)}
    override fun release(session:String){EvcAccessibilityService.instance?.release(session);UssdDeviceLease.release(session)}
}
