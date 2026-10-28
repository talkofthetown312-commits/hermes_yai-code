package com.hermespocket.app;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.util.Base64;
import android.webkit.JsPromptResult;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.widget.Toast;
import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;
import org.json.JSONObject;
import android.graphics.Color;
import android.os.Build;
import android.os.Bundle;
import android.view.View;
import android.view.WindowInsets;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.TextView;

public class MainActivity extends Activity {
    private WebView web;
    private FrameLayout content;
    private ValueCallback<Uri[]> fileSelection;
    private byte[] pendingSave;
    private static final int PICK_FILES = 51, SAVE_FILE = 52;
    private static final int MAX_FILE = 10 * 1024 * 1024;
    private static final String URL = "http://127.0.0.1:8766/";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        content = new FrameLayout(this);
        content.setBackgroundColor(Color.rgb(247, 248, 245));
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            content.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets safe = insets.getInsets(WindowInsets.Type.systemBars()
                    | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
                return WindowInsets.CONSUMED;
            });
        } else {
            content.setFitsSystemWindows(true);
        }
        setContentView(content);
        content.requestApplyInsets();
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::goBack);
        }
        openChat();
    }

    private void showView(View view) {
        content.removeAllViews();
        content.addView(view, new FrameLayout.LayoutParams(-1, -1));
        content.requestApplyInsets();
    }

    @SuppressLint("SetJavaScriptEnabled") // Required for local chat UI; loopback-only navigation,
    // strict server CSP, no JavascriptInterface, no file/content access, no remote scripts.
    private void openChat() {
        content.removeAllViews();
        if (web != null) web.destroy();
        web = new WebView(this);
        WebView.setWebContentsDebuggingEnabled(false);
        web.getSettings().setJavaScriptEnabled(true);
        web.getSettings().setDomStorageEnabled(true);
        web.getSettings().setUserAgentString(web.getSettings().getUserAgentString() + " HermesPocket/0.2.0");
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (!localPage(view.getUrl())) return false;
                if (fileSelection != null) fileSelection.onReceiveValue(null);
                fileSelection = callback;
                Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.setType("*/*");
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivityForResult(intent, PICK_FILES); }
                catch (Exception e) { callback.onReceiveValue(null); fileSelection = null; toast("No document picker available."); }
                return true;
            }
            @Override public boolean onJsPrompt(WebView view, String url, String message, String value, JsPromptResult result) {
                if (!localPage(url) || !"HERMES_POCKET_EXPORT".equals(message)) { result.cancel(); return true; }
                try {
                    if (value == null || value.length() > 14000000) throw new IllegalArgumentException("Export exceeds 10 MB.");
                    JSONObject obj = new JSONObject(value);
                    String action = obj.getString("action"), name = obj.getString("name"), mime = obj.getString("mime");
                    if (name.isEmpty() || name.length() > 160 || name.contains("/") || name.contains("\\") || name.matches(".*[\\x00-\\x1f\\x7f].*"))
                        throw new IllegalArgumentException("Invalid filename.");
                    if (!mime.matches("[a-zA-Z0-9.+-]+/[a-zA-Z0-9.+-]+")) throw new IllegalArgumentException("Invalid file type.");
                    byte[] data = Base64.decode(obj.getString("data"), Base64.NO_WRAP);
                    if (data.length > MAX_FILE) throw new IllegalArgumentException("Export exceeds 10 MB.");
                    if ("save".equals(action)) {
                        if (pendingSave != null) throw new IllegalArgumentException("Finish the previous save first.");
                        pendingSave = data;
                        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                        intent.addCategory(Intent.CATEGORY_OPENABLE);
                        intent.setType(mime);
                        intent.putExtra(Intent.EXTRA_TITLE, name);
                        try { startActivityForResult(intent, SAVE_FILE); }
                        catch (Exception e) { pendingSave = null; throw e; }
                    } else if ("share".equals(action)) {
                        File dir = new File(getCacheDir(), "exports");
                        if (!dir.isDirectory() && !dir.mkdirs()) throw new IllegalStateException("Cannot create share cache.");
                        File[] old = dir.listFiles();
                        if (old != null) for (File f : old) if (System.currentTimeMillis() - f.lastModified() > 86400000L) f.delete();
                        File file = new File(dir, java.util.UUID.randomUUID().toString() + "_" + name);
                        try (FileOutputStream stream = new FileOutputStream(file)) { stream.write(data); }
                        Uri uri = new Uri.Builder().scheme("content").authority(getPackageName() + ".exports").appendPath(file.getName()).build();
                        Intent intent = new Intent(Intent.ACTION_SEND);
                        intent.setType(mime);
                        intent.putExtra(Intent.EXTRA_STREAM, uri);
                        intent.setClipData(ClipData.newUri(getContentResolver(), name, uri));
                        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        startActivity(Intent.createChooser(intent, "Share " + name));
                    } else throw new IllegalArgumentException("Unknown export action.");
                    result.confirm("opened");
                } catch (Exception e) { result.confirm(e.getMessage() == null ? "Export could not be opened." : e.getMessage()); }
                return true;
            }
        });
        web.getSettings().setAllowFileAccess(false);
        web.getSettings().setAllowContentAccess(false);
        web.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                android.net.Uri u = request.getUrl();
                return !("http".equals(u.getScheme()) && "127.0.0.1".equals(u.getHost()) && u.getPort() == 8766);
            }
            @Override public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request.isForMainFrame()) showOffline();
            }
        });
        showView(web);
        web.loadUrl(URL);
    }

    private boolean localPage(String url) {
        if (url == null) return false;
        Uri uri = Uri.parse(url);
        return "http".equals(uri.getScheme()) && "127.0.0.1".equals(uri.getHost()) && uri.getPort() == 8766 && uri.getUserInfo() == null;
    }
    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_LONG).show(); }

    @SuppressWarnings("deprecation") // Platform SAF works on all supported API levels.
    @Override protected void onActivityResult(int request, int status, Intent intent) {
        super.onActivityResult(request, status, intent);
        if (request == PICK_FILES && fileSelection != null) {
            ArrayList<Uri> uris = new ArrayList<>();
            if (status == RESULT_OK && intent != null) {
                if (intent.getClipData() != null) {
                    ClipData clips = intent.getClipData();
                    for (int i = 0; i < Math.min(clips.getItemCount(), 6); i++) {
                        Uri uri = clips.getItemAt(i).getUri();
                        if (uri != null && "content".equals(uri.getScheme())) uris.add(uri);
                    }
                    if (clips.getItemCount() > 6) toast("Only the first six files were selected.");
                } else if (intent.getData() != null && "content".equals(intent.getData().getScheme())) uris.add(intent.getData());
            }
            fileSelection.onReceiveValue(uris.isEmpty() ? null : uris.toArray(new Uri[0]));
            fileSelection = null;
        }
        if (request == SAVE_FILE) {
            byte[] data = pendingSave; pendingSave = null;
            if (status == RESULT_OK && intent != null && intent.getData() != null && data != null && "content".equals(intent.getData().getScheme())) {
                Uri uri = intent.getData();
                new Thread(() -> {
                    try (OutputStream stream = getContentResolver().openOutputStream(uri, "wt")) {
                        if (stream == null) throw new IllegalStateException("No writable destination.");
                        stream.write(data);
                        runOnUiThread(() -> toast("File saved."));
                    } catch (Exception e) { runOnUiThread(() -> toast("Save failed. Try a different folder.")); }
                }).start();
            } else toast("Save cancelled.");
        }
    }

    private void showOffline() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(48, 48, 48, 48);
        TextView heading = new TextView(this);
        heading.setText(R.string.offline_title);
        heading.setTextSize(28);
        TextView body = new TextView(this);
        body.setText(R.string.offline_body);
        body.setTextIsSelectable(true);
        body.setTextSize(16);
        body.setPadding(0, 30, 0, 30);
        Button retry = new Button(this);
        retry.setText(R.string.reconnect);
        retry.setOnClickListener(v -> openChat());
        layout.addView(heading);
        layout.addView(body);
        layout.addView(retry);
        showView(layout);
    }

    private void goBack() {
        if (web != null && web.getParent() != null) {
            web.evaluateJavascript("(function(){var d=document.querySelector('dialog[open]');if(d){d.close();return true;}var s=document.getElementById('sidebar');if(s&&s.classList.contains('open')){s.classList.remove('open');return true;}return false;})()", handled -> {
                if (!"true".equals(handled)) { if (web.canGoBack()) web.goBack(); else finish(); }
            });
        } else finish();
    }
    @SuppressWarnings("deprecation") // Compatibility with Android 8-12.
    @Override public void onBackPressed() { goBack(); }
    @Override public void onDestroy() {
        if (fileSelection != null) { fileSelection.onReceiveValue(null); fileSelection = null; }
        pendingSave = null;
        if (content != null) content.removeAllViews();
        if (web != null) web.destroy();
        super.onDestroy();
    }
}
