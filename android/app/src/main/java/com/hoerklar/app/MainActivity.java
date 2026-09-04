package com.hoerklar.app;
import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.webkit.WebView;
import android.webkit.WebSettings;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.graphics.Color;
import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewClientCompat;
import org.schabi.newpipe.extractor.NewPipe;
import org.schabi.newpipe.extractor.ServiceList;
import org.schabi.newpipe.extractor.downloader.Downloader;
import org.schabi.newpipe.extractor.downloader.Request;
import org.schabi.newpipe.extractor.downloader.Response;
import org.schabi.newpipe.extractor.exceptions.ReCaptchaException;
import org.schabi.newpipe.extractor.stream.StreamInfo;
import java.io.IOException;
import java.net.URL;
import java.util.*;
import javax.net.ssl.HttpsURLConnection;

public class MainActivity extends Activity {
    private WebView wv;

    static class SimpleDownloader extends Downloader {
        @Override
        public Response execute(Request request) throws IOException, ReCaptchaException {
            HttpsURLConnection c = (HttpsURLConnection) new URL(request.url()).openConnection();
            c.setRequestMethod(request.httpMethod());
            if (request.headers() != null) {
                for (Map.Entry<String, List<String>> e : request.headers().entrySet()) {
                    c.setRequestProperty(e.getKey(), String.join(",", e.getValue()));
                }
            }
            if (request.dataToSend() != null) {
                c.setDoOutput(true);
                c.getOutputStream().write(request.dataToSend());
            }
            c.connect();
            String body = "";
            try {
                body = new String(c.getInputStream().readAllBytes(), java.nio.charset.StandardCharsets.UTF_8);
            } catch (Exception e) { body = ""; }
            return new Response(c.getResponseCode(), c.getResponseMessage(), c.getHeaderFields(), body, request.url());
        }
    }

    @Override protected void onCreate(Bundle s) {
        super.onCreate(s);
        try { NewPipe.init(new SimpleDownloader(), new org.schabi.newpipe.extractor.localization.Localization("en","GB")); } catch(Exception e){}
        final WebViewAssetLoader assetLoader = new WebViewAssetLoader.Builder()
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        wv = new WebView(this);
        wv.setBackgroundColor(Color.parseColor("#0a0e1e"));
        WebSettings ws = wv.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setMediaPlaybackRequiresUserGesture(false);
        ws.setAllowFileAccess(true);
        ws.setAllowContentAccess(true);
        ws.setAllowFileAccessFromFileURLs(true);
        ws.setAllowUniversalAccessFromFileURLs(true);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_COMPATIBILITY_MODE);
        ws.setUserAgentString("Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36");

        wv.setWebViewClient(new WebViewClientCompat() {
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest r) {
                try{
                    String u=r.getUrl().toString();
                    if(u.contains("localhost:8789/yt/") || u.contains("taalflix.local/yt/") || u.contains("hoerklar.local/yt/") || u.contains("hoerklar.onrender.com/yt/") || u.contains("taalflix.onrender.com/yt/")){
                        String vid=u.substring(u.lastIndexOf("/")+1).split("\\?")[0].split("&")[0];
                        StreamInfo info=StreamInfo.getInfo("https://www.youtube.com/watch?v="+vid);
                        String stream=null;
                        for(org.schabi.newpipe.extractor.stream.VideoStream vs: info.getVideoStreams()){
                            if(vs.getResolution().contains("360") || vs.getResolution().contains("480")){ stream=vs.getContent(); break; }
                        }
                        if(stream==null && !info.getVideoStreams().isEmpty()) stream=info.getVideoStreams().get(0).getContent();
                        if(stream!=null){
                            Map<String,String> h=new HashMap<>();
                            h.put("Location", stream);
                            h.put("Access-Control-Allow-Origin","*");
                            return new WebResourceResponse("text/plain","UTF-8",302,"Found",h,null);
                        }
                    }
                }catch(Exception e){}
                return assetLoader.shouldInterceptRequest(r.getUrl());
            }
            @Override public boolean shouldOverrideUrlLoading(WebView v, WebResourceRequest r) {
                return false;
            }
        });

        wv.setLayerType(View.LAYER_TYPE_HARDWARE, null);
        setContentView(wv);
        wv.loadUrl("https://abdomedo2033-code.github.io/HoerKlar/");
    }

    @Override public void onBackPressed() {
        if (wv.canGoBack()) wv.goBack(); else super.onBackPressed();
    }
}
