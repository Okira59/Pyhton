package com.okira.diptavan;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobInfo;
import android.app.job.JobParameters;
import android.app.job.JobScheduler;
import android.app.job.JobService;
import android.content.ComponentName;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.Locale;

/** Yaklaşık 15 dakikada bir botun panel verisini kontrol eder, yeni sinyal/kapanış varsa bildirim gösterir. */
public class SignalJob extends JobService {
    static final String DATA = BuildConfig.DATA;
    static final String CHANNEL = "sinyaller";
    static final int JOB_ID = 1;

    static void schedule(Context c) {
        JobScheduler js = c.getSystemService(JobScheduler.class);
        if (js.getPendingJob(JOB_ID) != null) return;
        js.schedule(new JobInfo.Builder(JOB_ID, new ComponentName(c, SignalJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPeriodic(15 * 60 * 1000L)
                .setPersisted(true)
                .build());
    }

    @Override
    public boolean onStartJob(JobParameters p) {
        new Thread(() -> {
            try {
                check(this);
            } catch (Exception ignored) {
                // ağ hatası: sonraki çalışmada tekrar denenir
            }
            jobFinished(p, false);
        }).start();
        return true;
    }

    @Override
    public boolean onStopJob(JobParameters p) {
        return true;
    }

    static void check(Context c) throws Exception {
        JSONArray hist = new JSONObject(get(DATA + "?t=" + System.currentTimeMillis())).getJSONArray("history");
        SharedPreferences prefs = c.getSharedPreferences("durum", MODE_PRIVATE);
        long last = prefs.getLong("last_t", -1), max = last;
        for (int i = 0; i < hist.length(); i++) {
            JSONObject e = hist.getJSONObject(i);
            long t = e.getLong("t");
            if (t > max) max = t;
            if (last >= 0 && t > last) notify(c, (int) t + i, e);
        }
        prefs.edit().putLong("last_t", max).apply();  // ilk çalışmada eski kayıtlar için bildirim gelmez
    }

    static void notify(Context c, int id, JSONObject e) throws Exception {
        boolean buy = e.getInt("dir") == 1;
        boolean fut = "futures".equals(BuildConfig.KIND);
        String sym = fut ? e.getString("sym").replace("USDT", "") : "XAU/USD";
        String side = fut ? (buy ? "LONG" : "SHORT") : (buy ? "AL" : "SAT");
        int dp = e.optInt("dp", 2);
        String title, text;
        if ("SINYAL".equals(e.getString("kind"))) {
            String what = "dip".equals(BuildConfig.KIND) ? (buy ? " (dip)" : " (tavan)") : "";
            title = (buy ? "🟢 " : "🔴 ") + side + what + " – " + sym;
            text = "Giriş: " + fmt(e.getDouble("price"), dp);
        } else {
            double entry = e.getDouble("entry"), exit = e.getDouble("exit");
            // futures: $20 teminatlı işlemin $ sonucu; altın: 1 pip = 1 $
            double pnl = fut ? e.optDouble("usd", e.getDouble("pct") * 0.2) : (buy ? 1 : -1) * (exit - entry);
            title = (pnl >= 0 ? "✅" : "❌") + " İŞLEM KAPANDI – " + sym + " " + side;
            text = fmt(entry, dp) + " → " + fmt(exit, dp) + String.format(Locale.US, "  (%+.2f$)  ", pnl)
                    + e.optString("reason");
        }
        NotificationManager nm = c.getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, c.getString(R.string.app_name) + " sinyalleri", NotificationManager.IMPORTANCE_HIGH));
        PendingIntent open = PendingIntent.getActivity(c, 0, new Intent(c, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE | PendingIntent.FLAG_UPDATE_CURRENT);
        nm.notify(id, new Notification.Builder(c, CHANNEL)
                .setSmallIcon(android.R.drawable.stat_notify_more)
                .setContentTitle(title)
                .setContentText(text)
                .setStyle(new Notification.BigTextStyle().bigText(text))
                .setContentIntent(open)
                .setAutoCancel(true)
                .build());
    }

    static String fmt(double v, int dp) {
        return String.format(Locale.US, "%." + dp + "f", v);
    }

    static String get(String url) throws Exception {
        HttpURLConnection con = (HttpURLConnection) new URL(url).openConnection();
        con.setConnectTimeout(15000);
        con.setReadTimeout(15000);
        try (InputStream in = con.getInputStream()) {
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] buf = new byte[8192];
            for (int n; (n = in.read(buf)) > 0; ) out.write(buf, 0, n);
            return out.toString("UTF-8");
        } finally {
            con.disconnect();
        }
    }
}
