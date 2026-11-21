# GitHub 建仓 + 首推 + 凭据入 GCM（之后 deploy.ps1 -WithGit 直接免密推送）
# 用法: .\push-github.ps1 -User <用户名> -Token <ghp_xxx> [-Private]
param(
  [Parameter(Mandatory=$true)][string]$User,
  [Parameter(Mandatory=$true)][string]$Token,
  [switch]$Private
)
$ErrorActionPreference = "Stop"
$root = "H:\新建文件夹\设计文件\樊清正\个人\rea\viewdl"
$repo = "viewdl"
$H = @{ Authorization = "Bearer $Token"; Accept = "application/vnd.github+json"; "X-GitHub-Api-Version" = "2022-11-28" }

# 1) 建仓（已存在则跳过）
$body = @{ name = $repo; description = "ViewDL: 全网视图解析下载（FastAPI + yt-dlp + 抖音/快手/小红书/微博专用解析器 + APK + 描述文件）"; private = [bool]$Private } | ConvertTo-Json
$resp = Invoke-RestMethod -Uri "https://api.github.com/user/repos" -Method Post -Headers $H -Body $body -ContentType "application/json"
Write-Host "仓库: $($resp.html_url)"

# 2) remote + 凭据入 GCM（后续推送免密）
git -C $root remote remove origin 2>$null
git -C $root remote add origin "https://github.com/$User/$repo.git"
git -C $root config credential.helper manager
"protocol=https`nhost=github.com`nusername=$User`npassword=$Token`n" | git credential approve

# 3) 推送
git -C $root push -u origin main
Write-Host "完成。以后热更新：.\deploy.ps1 -WithGit"
