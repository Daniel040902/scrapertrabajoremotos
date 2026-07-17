package com.example.novastream

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit

class JobNotificationService : Service() {

    private var scheduler: ScheduledExecutorService? = null
    private var lastCheckTime: String = ""

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
        lastCheckTime = getSharedPreferences("job_prefs", MODE_PRIVATE)
            .getString("last_check", "") ?: ""
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopSelf()
            return START_NOT_STICKY
        }

        startForeground(NOTIFICATION_ID, buildNotification("Buscando nuevos empleos remotos..."))
        startPolling()

        // Force a check immediately on start
        Thread { checkForNewJobs() }.start()

        return START_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun startPolling() {
        scheduler?.shutdownNow()
        scheduler = Executors.newSingleThreadScheduledExecutor()
        scheduler?.scheduleAtFixedRate({
            checkForNewJobs()
        }, 0, 30, TimeUnit.MINUTES)
    }

    private fun getApiUrl(): String = API_URL

    private fun checkForNewJobs() {
        try {
            val baseUrl = getApiUrl()
            val since = if (lastCheckTime.isNotEmpty()) {
                lastCheckTime
            } else {
                java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss'Z'", java.util.Locale.US)
                    .format(java.util.Date(System.currentTimeMillis() - 3 * 3600000))
            }
            val urlStr = "$baseUrl/jobs/new?since=$since"
            val urlStr = "$baseUrl/jobs/new?since=$since"

            val url = URL(urlStr)
            val conn = url.openConnection() as HttpURLConnection
            conn.connectTimeout = 15000
            conn.readTimeout = 15000
            conn.requestMethod = "GET"
            conn.setRequestProperty("Accept", "application/json")

            if (conn.responseCode == 200) {
                val response = conn.inputStream.bufferedReader().readText()
                val json = JSONObject(response)
                val jobs = json.getJSONArray("jobs")

                if (jobs.length() > 0) {
                    sendJobNotification(jobs)
                }

                lastCheckTime = java.text.SimpleDateFormat(
                    "yyyy-MM-dd'T'HH:mm:ss'Z'",
                    java.util.Locale.US
                ).format(java.util.Date())
                getSharedPreferences("job_prefs", MODE_PRIVATE)
                    .edit()
                    .putString("last_check", lastCheckTime)
                    .apply()

                updateForegroundNotification("Última revisión: ${jobs.length()} nuevos")
            }
            conn.disconnect()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun updateForegroundNotification(text: String) {
        val mgr = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        mgr.notify(NOTIFICATION_ID, buildNotification(text))
    }

    private fun sendJobNotification(jobs: JSONArray) {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        val openIntent = Intent(this, JobsActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPending = PendingIntent.getActivity(this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        val count = jobs.length()
        val title = if (count == 1) "1 nuevo empleo encontrado" else "$count nuevos empleos encontrados"

        val firstJob = jobs.getJSONObject(0)
        val body = buildString {
            append(firstJob.optString("title", "Empleo disponible"))
            append(" en ")
            append(firstJob.optString("company", "empresa"))
            if (count > 1) {
                append(" y ${count - 1} mas")
            }
        }

        val notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(NotificationCompat.BigTextStyle().bigText(body))
            .setContentIntent(openPending)
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setDefaults(NotificationCompat.DEFAULT_ALL)
            .setCategory(NotificationCompat.CATEGORY_EVENT)
            .build()

        manager.notify(NOTIFICATION_ID + 1, notification)
    }

    private fun buildNotification(text: String): android.app.Notification {
        val openIntent = Intent(this, JobsActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val openPending = PendingIntent.getActivity(this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)

        val stopIntent = PendingIntent.getService(this, 1,
            Intent(this, JobNotificationService::class.java).setAction(ACTION_STOP),
            PendingIntent.FLAG_IMMUTABLE)

        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle("NovaStream - Monitoreo")
            .setContentText(text)
            .setContentIntent(openPending)
            .addAction(android.R.drawable.ic_menu_close_clear_cancel, "Detener", stopIntent)
            .setOngoing(true)
            .setSilent(true)
            .build()
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Nuevos empleos remotos",
                NotificationManager.IMPORTANCE_HIGH
            ).apply {
                description = "Notificaciones cuando el scraper encuentra nuevas ofertas"
                enableVibration(true)
            }
            getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        scheduler?.shutdownNow()
    }

    companion object {
        const val CHANNEL_ID = "nova_job_notifications"
        const val NOTIFICATION_ID = 2001
        const val ACTION_STOP = "com.example.novastream.STOP_JOB_SERVICE"
        const val API_URL = "https://scrapertrabajoremotos-production.up.railway.app/api"

        fun start(context: Context) {
            val intent = Intent(context, JobNotificationService::class.java)
            context.startForegroundService(intent)
        }

        fun stop(context: Context) {
            val intent = Intent(context, JobNotificationService::class.java).apply {
                action = ACTION_STOP
            }
            context.startService(intent)
        }
    }
}
