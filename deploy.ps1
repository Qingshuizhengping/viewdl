# ViewDL 热更新部署：推送 GitHub（可选）+ 直推阿里云服务器 + 重启生效
# 用法: .\deploy.ps1            # 代码 → 服务器 → 重启 → 健康检查
#       .\deploy.ps1 -WithGit  # 同时 git push origin main
param([switch]$WithGit)

$ErrorActionPreference = "Stop"
$root  = "H:\新建文件夹\设计文件\樊清正\个人\rea\viewdl"
$srv   = "root@8.134.141.217"
$key   = "$env:USERPROFILE\.ssh\tunnel_doubao2"

Write-Host "== 1) 推送代码到服务器 =="
scp -o BatchMode=yes -i $key "$root\app.py" "$srv`:/opt/viewdl/app.py"
scp -o BatchMode=yes -i $key "$root\static\index.html" "$srv`:/opt/viewdl/static/index.html"
scp -o BatchMode=yes -i $key "$root\build_profile.py" "$srv`:/opt/viewdl/build_profile.py"

Write-Host "== 2) 重启服务（热更新生效） =="
ssh -o BatchMode=yes -i $key $srv "systemctl restart viewdl; sleep 3; systemctl is-active viewdl"

Write-Host "== 3) 健康检查 =="
ssh -o BatchMode=yes -i $key $srv "curl -s -o /dev/null -w 'api: %{http_code}\n' http://127.0.0.1:8771/api/jobs; curl -sk -H 'Host: coffee.weizhiyu.top' -o /dev/null -w 'web: %{http_code}\n' https://127.0.0.1/vdl/"

if ($WithGit) {
  Write-Host "== 4) git push =="
  git -C $root push origin main
}

Write-Host "完成。APK/描述文件无需重装，页面与解析能力已热更新。"
