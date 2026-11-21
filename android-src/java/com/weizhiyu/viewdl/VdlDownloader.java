package com.weizhiyu.viewdl;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ContentValues;
import android.content.Context;
import android.net.Uri;
import android.os.Environment;
import android.provider.MediaStore;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.widget.Toast;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/** Web 端"保存"：图片/视频直接写入系统相册（MediaStore），其它类型走系统下载器。 */
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
        final String kind = kindOf(url, mimeType);
        if ("other".equals(kind)) {
            enqueueSystem(url, userAgent);
            return;
        }
        final String name = fileNameOf(url, contentDisposition, kind);
        toast("保存中：" + name);
        final String fUrl = url;
        final String fUa = userAgent == null ? "" : userAgent;
        new Thread(() -> {
            try {
                HttpURLConnection c = (HttpURLConnection) new URL(fUrl).openConnection();
                c.setConnectTimeout(15000);
                c.setReadTimeout(120000);
                c.setInstanceFollowRedirects(true);
                String cookie = cm.getCookie(fUrl);
                if (cookie != null) c.setRequestProperty("Cookie", cookie);
                if (!fUa.isEmpty()) c.setRequestProperty("User-Agent", fUa);
                int code = c.getResponseCode();
                if (code >= 400) throw new Exception("HTTP " + code);
                String mime = c.getContentType();
                if (mime != null && mime.contains(";")) mime = mime.split(";")[0].trim();
                if (mime == null || mime.isEmpty()) mime = "image".equals(kind) ? "image/jpeg" : "video/mp4";
                boolean ok;
                if ("image".equals(kind)) {
                    ok = insert(MediaStore.Images.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                            "Pictures/ViewDL", name, mime, c);
                } else {
                    ok = insert(MediaStore.Video.Media.getContentUri(MediaStore.VOLUME_EXTERNAL_PRIMARY),
                            "Movies/ViewDL", name, mime, c);
                }
                final String msg = ok ? "已存入相册：" + name : "保存失败";
                toast(msg);
            } catch (Exception e) {
                toast("保存失败：" + e.getMessage());
            }
        }).start();
    }

    private boolean insert(Uri collection, String relPath, String name, String mime,
                           HttpURLConnection conn) throws Exception {
        android.content.ContentResolver cr = act.getContentResolver();
        ContentValues v = new ContentValues();
        v.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
        v.put(MediaStore.MediaColumns.MIME_TYPE, mime);
        v.put(MediaStore.MediaColumns.RELATIVE_PATH, relPath);
        v.put(MediaStore.MediaColumns.IS_PENDING, 1);
        Uri uri = cr.insert(collection, v);
        if (uri == null) return false;
        InputStream in = conn.getInputStream();
        OutputStream out = cr.openOutputStream(uri);
        if (out == null) { in.close(); return false; }
        byte[] buf = new byte[16384];
        int n;
        long total = 0;
        while ((n = in.read(buf)) > 0) { out.write(buf, 0, n); total += n; }
        out.close();
        in.close();
        ContentValues done = new ContentValues();
        done.put(MediaStore.MediaColumns.IS_PENDING, 0);
        cr.update(uri, done, null, null);
        return total > 0;
    }

    private String kindOf(String url, String mime) {
        String m = mime == null ? "" : mime.toLowerCase();
        String u = (url == null ? "" : url).toLowerCase();
        if (m.startsWith("image/") || u.contains(".jpg") || u.contains(".jpeg") || u.contains(".png")
                || u.contains(".webp") || u.contains(".gif") || u.contains(".heic")) return "image";
        if (m.startsWith("video/") || u.contains(".mp4") || u.contains(".mov") || u.contains(".m4v")
                || u.contains(".mkv")) return "video";
        return "other";
    }

    private String fileNameOf(String url, String cd, String kind) {
        String name = "";
        if (cd != null) {
            String p = cd.replace("\"", "");
            int i = p.indexOf("filename=");
            if (i >= 0) {
                name = p.substring(i + 9);
                int q = name.indexOf(';');
                if (q > 0) name = name.substring(0, q);
            }
        }
        if (name.isEmpty()) {
            String clean = url.split("[?#]")[0];
            int i = clean.lastIndexOf('/');
            name = i >= 0 ? clean.substring(i + 1) : "";
            if (name.length() > 40 || name.isEmpty()) name = "viewdl_" + System.currentTimeMillis();
        }
        if (!name.contains(".")) name += "image".equals(kind) ? ".jpg" : ".mp4";
        return name;
    }

    private void enqueueSystem(String url, String ua) {
        try {
            DownloadManager.Request r = new DownloadManager.Request(Uri.parse(url));
            String cookie = cm.getCookie(url);
            if (cookie != null) r.addRequestHeader("Cookie", cookie);
            if (ua != null) r.addRequestHeader("User-Agent", ua);
            r.setTitle("ViewDL 下载");
            r.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            r.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,
                    "viewdl_" + System.currentTimeMillis());
            ((DownloadManager) act.getSystemService(Context.DOWNLOAD_SERVICE)).enqueue(r);
            toast("已加入下载队列");
        } catch (Exception e) {
            toast("下载失败：" + e.getMessage());
        }
    }

    private void toast(String m) {
        act.runOnUiThread(() -> Toast.makeText(act, m, Toast.LENGTH_SHORT).show());
    }
}
