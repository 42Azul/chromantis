package org.chromantis.android;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.URI;
import java.net.URISyntaxException;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import javax.net.ssl.HttpsURLConnection;

final class ChromantisApi {
    private static final int MAX_JSON_BYTES = 1 << 20;
    private static final Pattern SESSION_COOKIE =
            Pattern.compile("^chromantis_family=([A-Za-z0-9_-]{43})(?:;|$)");

    final String origin;
    final String secret;

    ChromantisApi(String origin, String secret) {
        this.origin = parseOrigin(origin);
        this.secret = secret;
    }

    static String parseOrigin(String value) {
        try {
            URI uri = new URI(value.trim());
            String path = uri.getRawPath();
            if (!"https".equalsIgnoreCase(uri.getScheme())
                    || uri.getHost() == null
                    || (uri.getPort() != -1 && (uri.getPort() < 1 || uri.getPort() > 65535))
                    || uri.getRawUserInfo() != null
                    || uri.getRawQuery() != null
                    || uri.getRawFragment() != null
                    || (!path.isEmpty() && !"/".equals(path))) {
                throw new IllegalArgumentException();
            }
            // The authority matches the Host header and keeps session writes same-origin.
            int port = uri.getPort();
            return "https://"
                    + uri.getHost().toLowerCase(Locale.ROOT)
                    + (port == -1 || port == 443 ? "" : ":" + port);
        } catch (URISyntaxException | IllegalArgumentException error) {
            throw new IllegalArgumentException("Expected a private HTTPS server address.", error);
        }
    }

    ChromantisApi signIn(String code) throws IOException, JSONException {
        HttpsURLConnection connection = open("POST", "/family/session");
        try {
            writeJson(connection, new JSONObject().put("code", code));
            checkStatus(connection);
            for (var header : connection.getHeaderFields().entrySet()) {
                if (!"Set-Cookie".equalsIgnoreCase(header.getKey())) continue;
                for (String value : header.getValue()) {
                    Matcher match = SESSION_COOKIE.matcher(value);
                    if (match.find()) return new ChromantisApi(origin, match.group(1));
                }
            }
            throw new IOException("Family session cookie is missing.");
        } finally {
            connection.disconnect();
        }
    }

    JSONObject getJson(String route) throws IOException, JSONException {
        HttpsURLConnection connection = open("GET", route);
        try {
            checkStatus(connection);
            return new JSONObject(
                    new String(readBytes(connection, MAX_JSON_BYTES), StandardCharsets.UTF_8));
        } finally {
            connection.disconnect();
        }
    }

    void signOut() throws IOException {
        HttpsURLConnection connection = open("DELETE", "/family/session");
        try {
            checkStatus(connection);
        } finally {
            connection.disconnect();
        }
    }

    Bitmap loadPhoto(String path, boolean preview) throws IOException {
        String route = preview ? "/thumbnail" : "/image";
        HttpsURLConnection connection = open("GET", route + "?path=" + encode(path));
        try {
            checkStatus(connection);
            byte[] data = readBytes(connection, preview ? 1 << 20 : 32 << 20);
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inJustDecodeBounds = true;
            BitmapFactory.decodeByteArray(data, 0, data.length, options);
            int limit = preview ? 480 : 2048;
            options.inSampleSize = 1;
            while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > limit) {
                options.inSampleSize *= 2;
            }
            options.inJustDecodeBounds = false;
            Bitmap bitmap = BitmapFactory.decodeByteArray(data, 0, data.length, options);
            if (bitmap == null) throw new IOException("Invalid image data.");
            return bitmap;
        } finally {
            connection.disconnect();
        }
    }

    static String encode(String value) {
        try {
            return URLEncoder.encode(value, "UTF-8");
        } catch (java.io.UnsupportedEncodingException error) {
            throw new AssertionError(error);
        }
    }

    private HttpsURLConnection open(String method, String route) throws IOException {
        HttpsURLConnection connection =
                (HttpsURLConnection)
                        URI.create(origin + "/api/v1" + route).toURL().openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(6000);
        connection.setReadTimeout(8000);
        connection.setUseCaches(false);
        connection.setRequestMethod(method);
        if (secret != null) connection.setRequestProperty("Cookie", "chromantis_family=" + secret);
        if (!"GET".equals(method)) connection.setRequestProperty("Origin", origin);
        return connection;
    }

    private static void writeJson(HttpsURLConnection connection, JSONObject json)
            throws IOException {
        byte[] body = json.toString().getBytes(StandardCharsets.UTF_8);
        connection.setRequestProperty("Content-Type", "application/json");
        connection.setDoOutput(true);
        connection.setFixedLengthStreamingMode(body.length);
        try (OutputStream output = connection.getOutputStream()) {
            output.write(body);
        }
    }

    private static byte[] readBytes(HttpsURLConnection connection, int maxBytes)
            throws IOException {
        if (connection.getContentLengthLong() > maxBytes)
            throw new IOException("Response is too large.");
        try (InputStream input = connection.getInputStream()) {
            ByteArrayOutputStream output = new ByteArrayOutputStream();
            byte[] buffer = new byte[16384];
            int count;
            while ((count = input.read(buffer)) != -1) {
                if (output.size() + count > maxBytes)
                    throw new IOException("Response is too large.");
                output.write(buffer, 0, count);
            }
            return output.toByteArray();
        }
    }

    private static void checkStatus(HttpsURLConnection connection) throws IOException {
        int status = connection.getResponseCode();
        if (status < 200 || status >= 300) throw new HttpFailure(status);
    }

    static final class HttpFailure extends IOException {
        final int status;

        HttpFailure(int status) {
            super("Chromantis returned HTTP " + status);
            this.status = status;
        }
    }
}
