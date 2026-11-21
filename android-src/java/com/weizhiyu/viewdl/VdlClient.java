package com.weizhiyu.viewdl;

import android.content.Intent;
import android.net.Uri;
import android.webkit.WebView;
import android.webkit.WebViewClient;

/** 全部 http(s) 链接内部加载；其余 scheme 交给系统。 */
final class VdlClient extends WebViewClient {
    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
        if (url.startsWith("http://") || url.startsWith("https://")) {
            view.loadUrl(url);
            return true;
        }
        try {
            view.getContext().startActivity(new Intent(Intent.ACTION_VIEW, Uri.parse(url)));
        } catch (Exception ignored) { }
        return true;
    }
}
