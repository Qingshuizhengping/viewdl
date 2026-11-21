# ViewDL APK 构建管线：aapt2 → javac → d8 → zip → zipalign → apksigner
$ErrorActionPreference = "Stop"
$root = "H:\新建文件夹\设计文件\樊清正\个人\rea\viewdl"
$sdk  = "$root\android-sdk"
$src  = "$root\android-src"
$out  = "$root\apk-out"
New-Item -ItemType Directory -Force "$out\obj", "$out\dex" | Out-Null

# --- 动态定位工具 ---
$btDir  = (Get-ChildItem "$sdk\bt" -Directory | Where-Object { Test-Path "$($_.FullName)\aapt2.exe" } | Select-Object -First 1).FullName
$platJar = (Get-ChildItem "$sdk\plat" -Recurse -Filter "android.jar" | Select-Object -First 1).FullName
$java   = (Get-Command java).Source
$jdkBin = Split-Path $java
$javac  = "$jdkBin\javac.exe"
$keytool= "$jdkBin\keytool.exe"
"aapt2: $btDir"
"android.jar: $platJar"
if (-not $btDir -or -not $platJar) { throw "SDK 组件不完整" }
$aapt2    = "$btDir\aapt2.exe"
$d8       = "$btDir\d8.bat"
$zipalign = "$btDir\zipalign.exe"
$apksigner= "$btDir\apksigner.bat"

# --- 1. 资源 + Manifest → base.apk ---
& $aapt2 compile --dir "$src\res" -o "$out\res.zip"
& $aapt2 link -o "$out\base.apk" -I $platJar --manifest "$src\AndroidManifest.xml" `
    --min-sdk-version 24 --target-sdk-version 34 --version-code 1 --version-name "1.0" `
    "$out\res.zip" --auto-add-overlay
"link: $LASTEXITCODE"

# --- 2. javac ---
Get-ChildItem "$src\java" -Recurse -Filter *.java | ForEach-Object { $_.FullName } | Out-File "$out\sources.txt" -Encoding ascii
& $javac --release 8 -classpath $platJar -d "$out\obj" "@$out\sources.txt"
"javac: $LASTEXITCODE"

# --- 3. d8 → classes.dex ---
& $d8 --release --lib $platJar --output "$out\dex" (Get-ChildItem "$out\obj" -Recurse -Filter *.class | ForEach-Object { $_.FullName })
"d8: $LASTEXITCODE"
Test-Path "$out\dex\classes.dex"

# --- 4. classes.dex 注入 APK ---
$py = "$root\.venv\Scripts\python.exe"
& $py -c "import zipfile,sys; z=zipfile.ZipFile(r'$out\base.apk','a'); z.write(r'$out\dex\classes.dex','classes.dex',zipfile.ZIP_DEFLATED); z.close(); print('dex injected')"
"zip: $LASTEXITCODE"

# --- 5. zipalign ---
& $zipalign -f -p 4 "$out\base.apk" "$out\aligned.apk"
"zipalign: $LASTEXITCODE"

# --- 6. keystore（不存在则生成） + 签名 ---
$ks = "$root\viewdl.keystore"
if (-not (Test-Path $ks)) {
  & $keytool -genkeypair -alias viewdl -keyalg RSA -keysize 2048 -validity 10950 `
    -dname "CN=ViewDL,O=weizhiyu" -storepass viewdl123 -keypass viewdl123 -keystore $ks
  "keytool: $LASTEXITCODE"
}
& $apksigner sign --ks $ks --ks-pass pass:viewdl123 --key-pass pass:viewdl123 --out "$root\ViewDL-1.0.apk" "$out\aligned.apk"
"sign: $LASTEXITCODE"
& $apksigner verify --print-certs "$root\ViewDL-1.0.apk"
"verify: $LASTEXITCODE"
Get-Item "$root\ViewDL-1.0.apk" | Select-Object Name, @{n='KB';e={[math]::Round($_.Length/1KB,1)}}
