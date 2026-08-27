# TaalFlix Android

Built ✅ — APK ready

## APK location
`android/app/build/outputs/apk/debug/app-debug.apk` (22 MB)

This is a **WebView wrapper**: loads `standalone.html` offline from assets, plays remote video (YouTube/Archive/Vimeo) + embedded base64 audio segments. No rewrite needed.

## Install
1. On phone: Settings → Security → Allow install from unknown sources
2. Copy `app-debug.apk` to phone (USB / Telegram / Drive) → tap to install
3. Or via adb:
```
adb install android/app/build/outputs/apk/debug/app-debug.apk
```

## Open in Android Studio
File → Open → select `Dutch_App/android/` → Run ▶ (device/emulator)

Requires:
- JDK 17+ (you have 21)
- Android SDK 34, build-tools 34.0.0

## Rebuild
```
export JAVA_HOME=/home/deck/Applications/jdk
export ANDROID_HOME=/home/deck/Android/Sdk
./gradlew assembleDebug        # debug APK
./gradlew assembleRelease      # release (needs signing)
```

APK output: `app/build/outputs/apk/debug/`

## PWA (no APK needed)
`app/standalone.html` now has `manifest.json` + `sw.js`. On Android Chrome:
Open `standalone.html` via `https://` → ⋮ → Install app / Add to Home Screen.

For Play Store: use Bubblewrap TWA:
```
npx @bubblewrap/cli init --manifest https://yourdomain/manifest.json
npx @bubblewrap/cli build
```

## Notes
- `standalone.html` is 29MB (500+ clips with base64 audio). APK is 22MB compressed. For smaller APK, serve clips remotely and keep only HTML shell.
- Icon: `app/icon-512.png` → `mipmap-xxxhdpi/ic_launcher.png`
- Package: `com.taalflix.app` — change in `app/build.gradle` + `AndroidManifest.xml`
