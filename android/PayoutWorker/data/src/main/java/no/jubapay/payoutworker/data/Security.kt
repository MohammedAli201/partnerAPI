package no.jubapay.payoutworker.data

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.*
import java.security.spec.ECGenParameterSpec
import javax.crypto.*
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import org.json.JSONObject

interface RecordCipher { fun seal(value: String): String; fun open(value: String): String }
class KeystoreCipher: RecordCipher {
 private val alias="payout-records-v1"
 private val lock=Any()
 private fun key(): SecretKey = synchronized(lock) {
  val ks=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
  (ks.getKey(alias,null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
   init(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
    .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
  }.generateKey()
 }
 override fun seal(value: String): String { val c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());return b64(c.iv+c.doFinal(value.toByteArray())) }
 override fun open(value: String): String {val b=un64(value);require(b.size>28);val c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,b.copyOfRange(0,12)));return String(c.doFinal(b.copyOfRange(12,b.size)),Charsets.UTF_8)}
}
fun b64(bytes: ByteArray): String=Base64.encodeToString(bytes,Base64.NO_WRAP)
fun un64(s: String): ByteArray=Base64.decode(s,Base64.NO_WRAP)
class DeviceKey {
 private val alias="payout-enrollment-v1"
 @Synchronized private fun ensure(): KeyStore {
  val ks=KeyStore.getInstance("AndroidKeyStore").apply{load(null)}
  if(!ks.containsAlias(alias)) KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC,"AndroidKeyStore").apply {
   initialize(KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY).setAlgorithmParameterSpec(ECGenParameterSpec("secp256r1")).setDigests(KeyProperties.DIGEST_SHA256).build())
  }.generateKeyPair()
  return ks
 }
 fun publicKey(): String=b64(ensure().getCertificate(alias).publicKey.encoded)
 fun sign(message: String): String=Signature.getInstance("SHA256withECDSA").run {initSign(ensure().getKey(alias,null) as PrivateKey);update(message.toByteArray(Charsets.UTF_8));b64(sign())}
}
class Vault(context: Context, private val cipher: RecordCipher) {
 private val prefs=context.getSharedPreferences("protected-settings",Context.MODE_PRIVATE)
 @Synchronized fun get(name: String): String?=prefs.getString(name,null)?.let(cipher::open)
 @Synchronized fun put(name: String,value: String) { check(prefs.edit().putString(name,cipher.seal(value)).commit()) {"SETTINGS_WRITE_FAILED"} }
 @Synchronized fun remove(name: String) { check(prefs.edit().remove(name).commit()) {"SETTINGS_WRITE_FAILED"} }
}
/** PBKDF2 verifier, encrypted at rest; failure counter commits BEFORE each comparison. */
class OperatorPin(private val vault: Vault, private val now: ()->Long={System.currentTimeMillis()}) {
 fun configured()=vault.get("pin")!=null
 @Synchronized fun setup(pin: String,confirm: String) {
  require(!configured()); require(pin.matches(Regex("[0-9]{6,12}")) && pin==confirm) {"PIN_NEEDS_6_TO_12_MATCHING_DIGITS"}
  val salt=ByteArray(32).also(SecureRandom()::nextBytes)
  vault.put("pin",JSONObject().put("salt",b64(salt)).put("verifier",b64(derive(pin,salt))).put("failures",0).put("blocked_until",0).toString())
 }
 @Synchronized fun verify(pin: String): Boolean {
  val j=JSONObject(vault.get("pin") ?: return false)
  val time=now(); if(time<j.getLong("blocked_until")) return false
  val failures=(j.getInt("failures")+1).coerceAtMost(20)
  j.put("failures",failures).put("blocked_until",time+(if(failures<5)0L else (30_000L shl (failures-5).coerceAtMost(7)).coerceAtMost(3_600_000L)))
  vault.put("pin",j.toString())
  val ok=MessageDigest.isEqual(un64(j.getString("verifier")),derive(pin,un64(j.getString("salt"))))
  if(ok){j.put("failures",0).put("blocked_until",0);vault.put("pin",j.toString())}
  return ok
 }
 private fun derive(pin: String,salt: ByteArray): ByteArray {val spec=PBEKeySpec(pin.toCharArray(),salt,600_000,256);return try{SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1").generateSecret(spec).encoded}finally{spec.clearPassword()}}
}
