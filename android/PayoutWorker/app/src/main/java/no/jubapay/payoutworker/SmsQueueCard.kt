package no.jubapay.payoutworker

import android.Manifest
import android.content.Intent
import android.content.pm.PackageManager
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import androidx.core.content.ContextCompat

@Composable fun SmsQueueCard(vm:WorkerViewModel) {
 val context=LocalContext.current
 val running by vm.g.sms.running.collectAsState()
 val status by vm.g.sms.status.collectAsState()
 val history by vm.g.sms.history.collectAsState()
 var confirm by remember{mutableStateOf(false)}
 val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()){granted->if(granted)confirm=true}
 Card(Modifier.fillMaxWidth()){Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
  Text("Automatic SMS worker",style=MaterialTheme.typography.titleMedium)
  Text("Backend queues Message 1–10 to 97368681. One SMS is sent at a time on your default SMS SIM. The next waits for the previous send result to be saved.")
  Text(status)
  Button(enabled=!running,onClick={vm.touch();if(context.checkSelfPermission(Manifest.permission.SEND_SMS)!=PackageManager.PERMISSION_GRANTED)permission.launch(Manifest.permission.SEND_SMS)else confirm=true}){Text("Enable automatic SMS worker")}
  if(running)OutlinedButton(onClick={vm.g.sms.stop()}){Text("Stop after current SMS")}
  history.forEach{Text(it)}
 }}
 if(confirm)AlertDialog(onDismissRequest={confirm=false},title={Text("Enable automatic SMS execution?")},
  text={Text("The worker will wait for backend jobs and automatically send each test SMS on your default SMS SIM. The backend supplies the destination. Payment messages are labeled SMS TEST. Stop disables automatic execution.")},
  dismissButton={TextButton(onClick={confirm=false}){Text("Cancel")}},
  confirmButton={TextButton(onClick={confirm=false;vm.g.sms.enable();ContextCompat.startForegroundService(context,Intent(context,SmsSessionService::class.java))}){Text("Enable worker")}})
}
