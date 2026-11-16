package org.chromantis.android;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.graphics.Typeface;
import android.os.Build;
import android.os.Bundle;
import android.text.InputType;
import android.util.LruCache;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.AbsListView;
import android.widget.BaseAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.GridView;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.ScrollView;
import android.widget.TextView;
import android.window.OnBackInvokedDispatcher;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import javax.net.ssl.SSLException;

public final class ExplorerActivity extends Activity {
    private static final int PAGE_SIZE = 30;
    private static final int INK = 0xff1d3430;
    private static final int SUBTLE = 0xff475951;
    private static final int SURFACE = 0xfff5f7f1;

    private enum Level {
        YEARS,
        ALBUMS,
        SEARCH,
        PHOTOS,
        ORIGINAL
    }

    private static final class Page {
        final Level level;
        final String title;
        final String key;
        int offset;
        int position;
        int top;

        Page(Level level, String title, String key) {
            this.level = level;
            this.title = title;
            this.key = key;
        }
    }

    private static final class Entry {
        final String title;
        final String detail;
        final String key;

        Entry(String title, String detail, String key) {
            this.title = title;
            this.detail = detail;
            this.key = key;
        }
    }

    private final ArrayDeque<Page> pages = new ArrayDeque<>();
    private final ExecutorService requests = Executors.newSingleThreadExecutor();
    private final ThreadPoolExecutor previews =
            new ThreadPoolExecutor(
                    2,
                    2,
                    30,
                    TimeUnit.SECONDS,
                    new ArrayBlockingQueue<>(16),
                    new ThreadPoolExecutor.DiscardOldestPolicy());
    private final LruCache<String, Bitmap> thumbnails =
            new LruCache<>(4 * 1024 * 1024) {
                @Override
                protected int sizeOf(String key, Bitmap value) {
                    return value.getAllocationByteCount();
                }
            };

    private SharedPreferences settings;
    private ChromantisApi api;
    private LinearLayout root;
    private AbsListView list;
    private volatile int screen;

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        if (Build.VERSION.SDK_INT >= 33) {
            getOnBackInvokedDispatcher()
                    .registerOnBackInvokedCallback(
                            OnBackInvokedDispatcher.PRIORITY_DEFAULT, this::goBack);
        }
        previews.allowCoreThreadTimeOut(true);
        settings = getSharedPreferences("family_session", MODE_PRIVATE);
        String address = settings.getString("origin", "");
        String secret = settings.getString("session", null);
        if (secret != null) {
            try {
                api = new ChromantisApi(address, secret);
                showHome();
                return;
            } catch (IllegalArgumentException error) {
                settings.edit().remove("session").apply();
            }
        }
        showLogin("");
    }

    private void showLogin(String message) {
        pages.clear();
        resetScreen(getString(R.string.app_name), false);
        LinearLayout form = new LinearLayout(this);
        form.setOrientation(LinearLayout.VERTICAL);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(form);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        form.addView(text(R.string.connect_title, 20, INK, true));
        form.addView(text(R.string.address_label, 15, SUBTLE, false));
        EditText address = field(R.string.address_hint, InputType.TYPE_TEXT_VARIATION_URI);
        address.setText(settings.getString("origin", ""));
        form.addView(address);
        form.addView(text(R.string.code_label, 15, SUBTLE, false));
        EditText code = field(R.string.code_hint, InputType.TYPE_TEXT_VARIATION_PASSWORD);
        form.addView(code);
        TextView status = text(message, 15, SUBTLE, false);
        Button enter = new Button(this);
        enter.setText(R.string.sign_in);
        enter.setAllCaps(false);
        enter.setOnClickListener(
                view -> {
                    ChromantisApi endpoint;
                    try {
                        endpoint = new ChromantisApi(address.getText().toString(), null);
                    } catch (IllegalArgumentException error) {
                        status.setText(R.string.invalid_address);
                        return;
                    }
                    String invite = code.getText().toString().trim();
                    if (invite.isEmpty()) {
                        status.setText(R.string.missing_code);
                        return;
                    }
                    status.setText(R.string.connecting);
                    int ticket = screen;
                    enter.setEnabled(false);
                    code.setEnabled(false);
                    address.setEnabled(false);
                    requests.execute(
                            () -> {
                                try {
                                    ChromantisApi signedIn = endpoint.signIn(invite);
                                    deliver(
                                            ticket,
                                            () -> {
                                                api = signedIn;
                                                settings.edit()
                                                        .putString("origin", api.origin)
                                                        .putString("session", api.secret)
                                                        .apply();
                                                showHome();
                                            });
                                } catch (Exception error) {
                                    deliver(
                                            ticket,
                                            () -> {
                                                enter.setEnabled(true);
                                                code.setEnabled(true);
                                                address.setEnabled(true);
                                                status.setText(
                                                        hasStatus(error, 401)
                                                                ? getString(R.string.invalid_code)
                                                                : errorMessage(error));
                                            });
                                }
                            });
                });
        form.addView(enter);
        form.addView(status);
    }

    private void showHome() {
        pages.clear();
        pages.push(new Page(Level.YEARS, getString(R.string.folders), ""));
        showPage();
    }

    private void open(Page page) {
        if (list != null && list.getChildCount() > 0) {
            Page previous = pages.peek();
            previous.position = list.getFirstVisiblePosition();
            previous.top = list.getChildAt(0).getTop();
        }
        pages.push(page);
        showPage();
    }

    // Android 13 and later use the OnBackInvokedDispatcher registered in onCreate.
    @SuppressLint("GestureBackNavigation")
    @Override
    public void onBackPressed() {
        goBack();
    }

    private void goBack() {
        if (pages.size() > 1) {
            pages.pop();
            showPage();
        } else {
            finish();
        }
    }

    private void showPage() {
        Page page = pages.peek();
        if (page == null) return;
        resetScreen(page.title, pages.size() > 1);
        if (page.level == Level.YEARS) addSearch();
        if (page.level == Level.PHOTOS) root.addView(text(page.key, 14, SUBTLE, false));
        if (page.level == Level.ORIGINAL) {
            showOriginal(page.key);
            return;
        }
        TextView status = text(R.string.loading, 15, SUBTLE, false);
        root.addView(status);
        int ticket = screen;
        int offset = page.offset;
        ChromantisApi active = api;
        requests.execute(
                () -> {
                    try {
                        JSONObject response = active.getJson(routeFor(page, offset));
                        JSONArray items = response.getJSONArray("items");
                        List<Entry> entries = readEntries(page.level, items);
                        boolean next =
                                page.level == Level.PHOTOS
                                        ? !response.isNull("next_offset")
                                        : entries.size() > PAGE_SIZE;
                        boolean hasThumbnails =
                                page.level == Level.PHOTOS
                                        && active.getJson("/archive-status")
                                                .getJSONObject("item")
                                                .optBoolean("thumbnails");
                        deliver(
                                ticket,
                                () -> {
                                    root.removeView(status);
                                    displayEntries(page, entries, next, hasThumbnails);
                                });
                    } catch (Exception error) {
                        deliver(ticket, () -> showRequestError(active, status, error));
                    }
                });
    }

    private static String routeFor(Page page, int offset) {
        if (page.level == Level.YEARS) return "/years";
        String key = ChromantisApi.encode(page.key);
        if (page.level == Level.PHOTOS) {
            return "/album-images?path=" + key + "&limit=" + PAGE_SIZE + "&offset=" + offset;
        }
        return "/folders?q=" + key + "&limit=" + (PAGE_SIZE + 1) + "&offset=" + offset;
    }

    private List<Entry> readEntries(Level level, JSONArray items) throws JSONException {
        List<Entry> entries = new ArrayList<>();
        for (int i = 0; i < items.length(); i++) {
            JSONObject item = items.getJSONObject(i);
            if (level == Level.YEARS) {
                String year = item.getString("year");
                int folders = item.getInt("folders");
                String detail =
                        getResources().getQuantityString(R.plurals.album_count, folders, folders);
                entries.add(new Entry(year, detail, year));
            } else {
                String path = item.getString("path");
                String title =
                        level == Level.PHOTOS
                                ? path.substring(path.lastIndexOf('/') + 1)
                                : item.getString("title");
                entries.add(new Entry(title, level == Level.PHOTOS ? "" : path, path));
            }
        }
        return entries;
    }

    private void displayEntries(
            Page page, List<Entry> fetched, boolean next, boolean hasThumbnails) {
        List<Entry> entries =
                page.level == Level.YEARS
                        ? fetched
                        : fetched.subList(0, Math.min(PAGE_SIZE, fetched.size()));
        if (entries.isEmpty()) root.addView(text(R.string.no_results, 16, SUBTLE, false));
        if (page.level == Level.PHOTOS) {
            if (!hasThumbnails && !entries.isEmpty()) {
                root.addView(text(R.string.open_photo_hint, 14, SUBTLE, false));
            }
            GridView grid = new GridView(this);
            grid.setNumColumns(GridView.AUTO_FIT);
            grid.setColumnWidth(dp(110));
            grid.setHorizontalSpacing(dp(8));
            grid.setVerticalSpacing(dp(8));
            list = grid;
        } else {
            list = new ListView(this);
        }
        list.setAdapter(new ExplorerAdapter(entries, page.level == Level.PHOTOS, hasThumbnails));
        list.setOnItemClickListener(
                (parent, view, position, id) -> {
                    Entry entry = entries.get(position);
                    switch (page.level) {
                        case YEARS -> open(new Page(Level.ALBUMS, entry.title, entry.key));
                        case PHOTOS -> open(new Page(Level.ORIGINAL, entry.title, entry.key));
                        default -> open(new Page(Level.PHOTOS, entry.title, entry.key));
                    }
                });
        root.addView(list, new LinearLayout.LayoutParams(-1, 0, 1));
        if (page.position > 0 || page.top != 0) list.setSelectionFromTop(page.position, page.top);
        if (page.offset > 0 || next) {
            LinearLayout controls = new LinearLayout(this);
            if (page.offset > 0)
                controls.addView(button(R.string.previous, () -> movePage(-PAGE_SIZE)));
            if (next) controls.addView(button(R.string.next, () -> movePage(PAGE_SIZE)));
            root.addView(controls);
        }
    }

    private void addSearch() {
        LinearLayout row = new LinearLayout(this);
        EditText query = field(R.string.search_hint, 0);
        row.addView(query, new LinearLayout.LayoutParams(0, -2, 1));
        row.addView(
                button(
                        R.string.search,
                        () -> {
                            String value = query.getText().toString().trim();
                            if (!value.isEmpty()) {
                                query.clearFocus();
                                getSystemService(android.view.inputmethod.InputMethodManager.class)
                                        .hideSoftInputFromWindow(query.getWindowToken(), 0);
                                open(new Page(Level.SEARCH, getString(R.string.results), value));
                            }
                        }));
        root.addView(row);
        Button signOut = button(R.string.sign_out, this::signOut);
        root.addView(signOut);
    }

    private void movePage(int delta) {
        Page page = pages.peek();
        page.offset += delta;
        page.position = 0;
        page.top = 0;
        showPage();
    }

    private void showOriginal(String path) {
        TextView status = text(R.string.opening_photo, 15, SUBTLE, false);
        root.addView(status);
        int ticket = screen;
        ChromantisApi active = api;
        requests.execute(
                () -> {
                    try {
                        Bitmap bitmap = active.loadPhoto(path, false);
                        deliver(
                                ticket,
                                () -> {
                                    root.removeView(status);
                                    ImageView image = new ImageView(this);
                                    image.setContentDescription(pages.peek().title);
                                    image.setScaleType(ImageView.ScaleType.FIT_CENTER);
                                    image.setImageBitmap(bitmap);
                                    root.addView(image, new LinearLayout.LayoutParams(-1, 0, 1));
                                });
                    } catch (Exception error) {
                        deliver(ticket, () -> showRequestError(active, status, error));
                    }
                });
    }

    private void showRequestError(ChromantisApi active, TextView status, Exception error) {
        if (hasStatus(error, 401)) expireSession(active);
        else {
            status.setText(errorMessage(error));
            root.addView(button(R.string.retry, this::showPage));
        }
    }

    private void signOut() {
        resetScreen(getString(R.string.app_name), false);
        TextView status = text(R.string.closing_session, 15, SUBTLE, false);
        root.addView(status);
        int ticket = screen;
        ChromantisApi active = api;
        requests.execute(
                () -> {
                    try {
                        active.signOut();
                        deliver(ticket, () -> clearSession(""));
                    } catch (Exception error) {
                        deliver(
                                ticket,
                                () -> {
                                    status.setText(errorMessage(error));
                                    root.addView(button(R.string.retry, this::signOut));
                                    root.addView(button(R.string.back_to_folders, this::showHome));
                                });
                    }
                });
    }

    private void expireSession(ChromantisApi active) {
        if (api == active) clearSession(getString(R.string.expired_session));
    }

    private void clearSession(String message) {
        api = null;
        settings.edit().remove("session").apply();
        thumbnails.evictAll();
        showLogin(message);
    }

    private static boolean hasStatus(Exception error, int status) {
        return error instanceof ChromantisApi.HttpFailure failure && failure.status == status;
    }

    private String errorMessage(Exception error) {
        if (error instanceof SSLException) return getString(R.string.untrusted_certificate);
        if (hasStatus(error, 404) || hasStatus(error, 422))
            return getString(R.string.content_unavailable);
        if (hasStatus(error, 403)) return getString(R.string.operation_forbidden);
        return getString(R.string.request_failed);
    }

    private void deliver(int ticket, Runnable render) {
        runOnUiThread(
                () -> {
                    if (!isFinishing() && !isDestroyed() && ticket == screen) render.run();
                });
    }

    private void resetScreen(String title, boolean back) {
        screen++;
        previews.getQueue().clear();
        list = null;
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(SURFACE);
        root.setOnApplyWindowInsetsListener(
                (view, insets) -> {
                    if (Build.VERSION.SDK_INT >= 30) {
                        android.graphics.Insets bars =
                                insets.getInsets(
                                        WindowInsets.Type.systemBars()
                                                | WindowInsets.Type.displayCutout()
                                                | WindowInsets.Type.ime());
                        view.setPadding(
                                dp(16) + bars.left,
                                dp(8) + bars.top,
                                dp(16) + bars.right,
                                dp(8) + bars.bottom);
                    } else {
                        view.setPadding(dp(16), dp(8), dp(16), dp(8));
                    }
                    return insets;
                });
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        if (back) header.addView(button(R.string.back, this::goBack));
        TextView heading = text(title, 25, INK, true);
        heading.setPadding(dp(8), dp(12), 0, dp(12));
        header.addView(heading, new LinearLayout.LayoutParams(0, -2, 1));
        root.addView(header);
        setContentView(root);
    }

    private EditText field(int hint, int variation) {
        EditText field = new EditText(this);
        field.setHint(hint);
        field.setInputType(InputType.TYPE_CLASS_TEXT | variation);
        field.setSingleLine(true);
        return field;
    }

    private Button button(int label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        return view;
    }

    private TextView text(int value, int size, int color, boolean bold) {
        return text(getString(value), size, color, bold);
    }

    private int dp(int pixels) {
        return Math.round(pixels * getResources().getDisplayMetrics().density);
    }

    @Override
    protected void onDestroy() {
        screen++;
        requests.shutdownNow();
        previews.shutdownNow();
        super.onDestroy();
    }

    private final class ExplorerAdapter extends BaseAdapter {
        private final List<Entry> entries;
        private final boolean grid;
        private final boolean hasThumbnails;

        ExplorerAdapter(List<Entry> entries, boolean grid, boolean hasThumbnails) {
            this.entries = entries;
            this.grid = grid;
            this.hasThumbnails = hasThumbnails;
        }

        @Override
        public int getCount() {
            return entries.size();
        }

        @Override
        public Entry getItem(int position) {
            return entries.get(position);
        }

        @Override
        public long getItemId(int position) {
            return position;
        }

        @Override
        public View getView(int position, View recycled, ViewGroup parent) {
            Entry entry = getItem(position);
            LinearLayout cell = new LinearLayout(ExplorerActivity.this);
            cell.setOrientation(LinearLayout.VERTICAL);
            cell.setPadding(dp(8), dp(10), dp(8), dp(10));
            if (grid) {
                ImageView image = new ImageView(ExplorerActivity.this);
                image.setBackgroundColor(0xffe3ebdf);
                image.setScaleType(ImageView.ScaleType.CENTER_CROP);
                image.setContentDescription(entry.title);
                cell.addView(image, new LinearLayout.LayoutParams(-1, dp(100)));
                if (hasThumbnails) loadThumbnail(entry.key, image);
            }
            TextView title = text(entry.title, 16, INK, true);
            cell.addView(title);
            if (!entry.detail.isEmpty()) cell.addView(text(entry.detail, 13, SUBTLE, false));
            return cell;
        }
    }

    private void loadThumbnail(String path, ImageView image) {
        Bitmap cached = thumbnails.get(path);
        if (cached != null) {
            image.setImageBitmap(cached);
            return;
        }
        int ticket = screen;
        ChromantisApi active = api;
        previews.execute(
                () -> {
                    if (ticket != screen) return;
                    try {
                        Bitmap thumbnail = active.loadPhoto(path, true);
                        deliver(
                                ticket,
                                () -> {
                                    thumbnails.put(path, thumbnail);
                                    image.setImageBitmap(thumbnail);
                                });
                    } catch (Exception error) {
                        if (hasStatus(error, 401)) deliver(ticket, () -> expireSession(active));
                        else
                            deliver(
                                    ticket,
                                    () ->
                                            image.setContentDescription(
                                                    getString(R.string.thumbnail_unavailable)));
                    }
                });
    }
}
