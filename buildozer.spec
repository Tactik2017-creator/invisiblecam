[app]
title = InvisibleCam
package.name = invisiblecam
package.domain = org.myhome
source.dir = .
source.include_exts = py,png,jpg,kv,atlas
version = 1.0
requirements = python3,kivy==2.3.0,numpy,camera4kivy,gestures4kivy
orientation = portrait
fullscreen = 0

android.permissions = CAMERA
android.api = 33
android.minapi = 24
android.archs = arm64-v8a
android.allow_backup = True
android.accept_sdk_license = True
p4a.hook = camerax_provider/gradle_options.py

[buildozer]
log_level = 2
warn_on_root = 1
