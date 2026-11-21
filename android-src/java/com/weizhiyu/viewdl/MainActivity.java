package com.weizhiyu.viewdl;

import android.app.Activity;
import android.app.DownloadManager;
import android.os.Bundle;
import android.view.View;
import android.webkit.CookieManager;
import android.webkit.WebView;
import android.webkit.WebSettings;

public class MainActivity extends Activity {

    private WebView wv;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        wv = new WebView(this);
        setContentView(wv);
        getWindow().setStatusBarColor(0xFFF7F7F5);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);

        WebSettings s = wv.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setUseWideViewPort(true);
        s.setLoadWithOverviewMode(true);

        CookieManager cm = CookieManager.getInstance();
        cm.setAcceptCookie(true);
        cm.setAcceptThirdPartyCookies(wv, true);

        wv.setWebViewClient(new VdlClient());
        wv.setDownloadListener(new VdlDownloader(this, cm));
        wv.loadUrl("https://coffee.weizhiyu.top/vdl/");
    }

    @Override
    public void onBackPressed() {
        if (wv != null && wv.canGoBack()) wv.goBack(); else super.onBackPressed();
    }
}
