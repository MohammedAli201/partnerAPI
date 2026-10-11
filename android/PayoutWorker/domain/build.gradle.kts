plugins { id("org.jetbrains.kotlin.jvm") }
kotlin { jvmToolchain(17); compilerOptions { jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_11) } }
java { sourceCompatibility=JavaVersion.VERSION_11; targetCompatibility=JavaVersion.VERSION_11 }
dependencies {
 implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.10.2")
 testImplementation("junit:junit:4.13.2")
 testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.10.2")
}
