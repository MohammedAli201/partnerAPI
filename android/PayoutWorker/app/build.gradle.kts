plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "no.jubapay.payoutworker"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "no.jubapay.payoutworker"
        minSdk = 24
        targetSdk = 37
        versionCode = 3
        versionName = "1.2"
        buildConfigField("String", "PROVISIONED_BACKEND", "\"${providers.environmentVariable("PAYOUT_BACKEND_URL").getOrElse("")}\"")
        buildConfigField("String", "PROVISIONED_ENROLLMENT", "\"${providers.environmentVariable("PAYOUT_ENROLLMENT_CODE").getOrElse("")}\"")

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        create("directInstall") {
            initWith(getByName("release"))
            isDebuggable = false
            // Preserve the existing testing signer so updates retain device enrollment.
            // This is a signed testing distribution, not a production signing identity.
            signingConfig = signingConfigs.getByName("debug")
            optimization { enable = false }
            matchingFallbacks += listOf("release")
        }
        release {
            optimization {
                enable = true
                packageScope = setOf("androidx.**", "kotlin.**", "kotlinx.**")
            }
        }
    }
    splits {
        abi { isEnable = false }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":domain"))
    implementation(project(":data"))
    implementation(project(":device"))
    implementation("androidx.room:room-runtime:2.8.5")
    implementation("androidx.work:work-runtime-ktx:2.10.5")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.10.2")

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}
