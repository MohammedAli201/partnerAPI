package no.jubapay.payoutworker

import android.app.*
import android.content.Intent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.pm.PackageManager
import android.Manifest
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import kotlinx.coroutines.*

class SmsSessionService:Service() {
 private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
 private var task:Job?=null
 private val worker get()=(application as WorkerApplication).graph.sms
 override fun onBind(intent:Intent?)=null
 override fun onStartCommand(intent:Intent?,flags:Int,startId:Int):Int {
  if(!worker.enabled()){stopSelf();return START_NOT_STICKY}
  if(task?.isActive==true)return START_STICKY
  val nm=getSystemService(NotificationManager::class.java)
  if(Build.VERSION.SDK_INT>=26)nm.createNotificationChannel(NotificationChannel("sms-queue","SMS test queue",NotificationManager.IMPORTANCE_LOW))
  val open=PendingIntent.getActivity(this,0,Intent(this,MainActivity::class.java),PendingIntent.FLAG_IMMUTABLE)
  startForeground(18,NotificationCompat.Builder(this,"sms-queue").setSmallIcon(android.R.drawable.stat_notify_sync)
   .setContentTitle("Automatic SMS worker enabled").setContentText("Waiting for backend jobs; one SMS at a time").setOngoing(true).setContentIntent(open).build())
  task=scope.launch {
   try {
    while(isActive && worker.enabled()) {
     try{worker.run()}catch(_:Exception){worker.status.value="SMS worker unavailable: check permission and default SMS SIM"}
     if(worker.enabled())delay(5_000)
    }
   } finally{stopForeground(STOP_FOREGROUND_REMOVE);stopSelf()}
  }
  return START_STICKY
 }
 override fun onTimeout(startId:Int,fgsType:Int){worker.stop();scope.cancel();stopSelf()}
 override fun onDestroy(){scope.cancel();super.onDestroy()}
}

class SmsResumeReceiver:BroadcastReceiver() {
 override fun onReceive(context:Context,intent:Intent) {
  if(intent.action !in setOf(Intent.ACTION_BOOT_COMPLETED,Intent.ACTION_MY_PACKAGE_REPLACED))return
  val g=(context.applicationContext as WorkerApplication).graph
  if(g.sms.enabled()&&g.backend.enrolled()&&context.checkSelfPermission(Manifest.permission.SEND_SMS)==PackageManager.PERMISSION_GRANTED) {
   try{ContextCompat.startForegroundService(context,Intent(context,SmsSessionService::class.java))}
   catch(_:Exception){g.sms.status.value="Resume the automatic SMS worker from the app"}
  }
 }
}
