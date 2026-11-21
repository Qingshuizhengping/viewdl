package com.weizhiyu.viewdl;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.widget.Toast;

/** Web 端"保存"按钮的下载交给系统 DownloadManager（带 Cookie/UA，存公共 Downloads）。 */
final class VdlDownloader implements DownloadListener {

    private final Activity act;
    private final CookieManager cm;

    VdlDownloader(Activity act, CookieManager cm) {
        this.act = act;
        this.cm = cm;
    }

    @Override
    public void onDownloadStart(String url, String userAgent, String contentDisposition,
                                String mimeType, long contentLength) {
        try {
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            String cookie = cm.getCookie(url);
            if (cookie != null) r.addRequestHeader("Cookie", cookie);
            if (userAgent != null) r.addRequestHeader("User-Agent", userAgent);
            String name = "viewdl_" + System.currentTimeMillis();
            if (contentDisposition != null) {
                String p = contentDisposition.replace("\"", "");
                int i = p.indexOf("filename=");
                if (i >= 0) {
                    name = p.substring(i + 9);
                    int q = name.indexOf(';');
                    if (q > 0) name = name.substring(0, q);
                }
            }
            r.setTitle(name);
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            ((DownloadManager) act.getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
            Toast.makeText(act, "已加入下载：" + name, Toast.LENGTH_SHORT).show();
        } catch (Exception e) {
            Toast.makeText(act, "下载失败：" + e.getMessage(), Toast.LENGTH_SHORT).show();
        }
    }
}
