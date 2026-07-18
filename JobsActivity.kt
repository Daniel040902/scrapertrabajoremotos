package com.example.novastream

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.AdapterView
import android.widget.ArrayAdapter
import android.widget.ImageButton
import android.widget.LinearLayout
import android.widget.Spinner
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.button.MaterialButton
import com.google.android.material.card.MaterialCardView
import com.google.android.material.chip.ChipGroup
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlin.concurrent.thread

class JobsActivity : AppCompatActivity() {

    private val allJobs = mutableListOf<JSONObject>()
    private val filteredJobs = mutableListOf<JSONObject>()
    private lateinit var adapter: JobAdapter
    private lateinit var recycler: RecyclerView
    private lateinit var emptyContainer: LinearLayout
    private lateinit var loadingBar: View
    private lateinit var statusText: TextView
    private lateinit var statsText: TextView
    private lateinit var spinnerTime: Spinner
    private lateinit var spinnerSource: Spinner

    private val API_URL = "https://scrapertrabajoremotos-production.up.railway.app/api/jobs"
    private var isLoading = false
    private var currentOffset = 0
    private val pageSize = 200
    private var totalAvailable = 0

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_jobs)

        recycler = findViewById(R.id.jobs_recycler)
        emptyContainer = findViewById(R.id.empty_container)
        loadingBar = findViewById(R.id.loading_bar)
        statusText = findViewById(R.id.status_text)
        statsText = findViewById(R.id.stats_text)
        spinnerTime = findViewById(R.id.spinner_time)
        spinnerSource = findViewById(R.id.spinner_source)
        val btnRefresh = findViewById<ImageButton>(R.id.btn_refresh)
        val btnRetry = findViewById<MaterialButton>(R.id.btn_retry)

        val layoutManager = LinearLayoutManager(this)
        recycler.layoutManager = layoutManager
        adapter = JobAdapter()
        recycler.adapter = adapter

        recycler.addOnScrollListener(object : RecyclerView.OnScrollListener() {
            override fun onScrolled(rv: RecyclerView, dx: Int, dy: Int) {
                if (dy <= 0 || isLoading) return
                val visible = layoutManager.childCount
                val past = layoutManager.findFirstVisibleItemPosition()
                val total = layoutManager.itemCount
                if (past + visible >= total - 3 && total < totalAvailable) {
                    loadMoreJobs()
                }
            }
        })

        btnRefresh.setOnClickListener { loadJobs() }
        btnRetry.setOnClickListener { loadJobs() }
        setupFilters()
        JobNotificationService.start(this)
        loadJobs()
    }

    private fun setupFilters() {
        findViewById<ChipGroup>(R.id.chip_group_category)
            .setOnCheckedStateChangeListener { _, _ -> applyFilters() }

        spinnerTime.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            arrayOf("Siempre", "Últ. 2 días", "Última semana"))
        spinnerTime.setSelection(1)
        spinnerSource.adapter = ArrayAdapter(this, android.R.layout.simple_spinner_dropdown_item,
            arrayOf("Todas", "LinkedIn", "RemoteJobs.org", "Himalayas", "Remotive", "Arbeitnow", "RemoteOK", "JobsBase"))

        val listener = object : AdapterView.OnItemSelectedListener {
            override fun onItemSelected(p: AdapterView<*>?, v: View?, i: Int, l: Long) { applyFilters() }
            override fun onNothingSelected(p: AdapterView<*>?) {}
        }
        spinnerTime.onItemSelectedListener = listener
        spinnerSource.onItemSelectedListener = listener
    }

    private fun getCategory(): String? = when {
        findViewById<ChipGroup>(R.id.chip_group_category).checkedChipIds.firstOrNull() == R.id.chip_junior -> "junior"
        findViewById<ChipGroup>(R.id.chip_group_category).checkedChipIds.firstOrNull() == R.id.chip_pasantia -> "pasantia"
        else -> null
    }

    private fun getTime(): String? = when (spinnerTime.selectedItemPosition) {
        1 -> "recientes"; 2 -> "semana"; else -> null
    }

    private fun getSource(): String? = when (spinnerSource.selectedItemPosition) {
        1 -> "LinkedIn"; 2 -> "RemoteJobs.org"; 3 -> "Himalayas"; 4 -> "Remotive"; 5 -> "Arbeitnow"; 6 -> "RemoteOK"; 7 -> "JobsBase"; else -> null
    }

    private fun parseIso(iso: String): Long = try {
        if (iso.length >= 19) {
            SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US).parse(iso.substring(0, 19))?.time ?: 0
        } else if (iso.length >= 10) {
            SimpleDateFormat("yyyy-MM-dd", Locale.US).parse(iso.substring(0, 10))?.time ?: 0
        } else 0
    } catch (_: Exception) { 0 }

    private fun passTime(job: JSONObject, filter: String?): Boolean {
        if (filter == null) return true
        val ahora = System.currentTimeMillis()
        val posted = job.optString("posted_date", "")
        if (filter == "recientes") {
            val hoy = java.text.SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date(ahora))
            val ayer = java.text.SimpleDateFormat("yyyy-MM-dd", Locale.US).format(java.util.Date(ahora - 86400000))
            return posted.startsWith(hoy) || posted.startsWith(ayer)
        }
        if (filter == "semana") {
            val sem = ahora - 7L * 86400000
            return parseIso(posted) >= sem || parseIso(job.optString("scraped_at", "")) >= sem
        }
        return true
    }

    private fun applyFilters() {
        filteredJobs.clear()
        val cat = getCategory()
        val time = getTime()
        val src = getSource()
        for (job in allJobs) {
            if (cat != null && job.optString("category") != cat) continue
            if (!passTime(job, time)) continue
            if (src != null && !job.optString("source", "").equals(src, true)) continue
            filteredJobs.add(job)
        }
        adapter.notifyDataSetChanged()
        updateStats()
        updateEmptyState()
    }

    private fun loadJobs() {
        currentOffset = 0; allJobs.clear(); filteredJobs.clear()
        adapter.notifyDataSetChanged()
        loadJobsFromUrl("${API_URL.split("?")[0]}?limit=$pageSize&offset=$currentOffset", true)
    }

    private fun loadMoreJobs() {
        if (isLoading) return
        currentOffset += pageSize
        loadJobsFromUrl("${API_URL.split("?")[0]}?limit=$pageSize&offset=$currentOffset", false)
    }

    private fun loadJobsFromUrl(url: String, clearFirst: Boolean) {
        if (isLoading) return
        isLoading = true; loadingBar.visibility = View.VISIBLE; emptyContainer.visibility = View.GONE
        thread {
            try {
                val conn = URL(url).openConnection() as HttpURLConnection
                conn.connectTimeout = 10000; conn.readTimeout = 10000
                conn.requestMethod = "GET"; conn.setRequestProperty("Accept", "application/json")
                if (conn.responseCode == 200) {
                    val json = JSONObject(conn.inputStream.bufferedReader().readText())
                    totalAvailable = json.optInt("total", 0)
                    val arr = json.getJSONArray("jobs")
                    runOnUiThread {
                        for (i in 0 until arr.length()) allJobs.add(arr.getJSONObject(i))
                        applyFilters()
                        loadingBar.visibility = View.GONE
                        statusText.text = "${allJobs.size} empleos cargados"
                        isLoading = false
                    }
                } else {
                    runOnUiThread { loadingBar.visibility = View.GONE; statusText.text = "Error ${conn.responseCode}"; updateEmptyState(); isLoading = false }
                }
                conn.disconnect()
            } catch (e: Exception) {
                runOnUiThread {
                    loadingBar.visibility = View.GONE
                    statusText.text = if ((e.message ?: "").contains("timeout", true)) "Tiempo de espera agotado" else "Error de conexión"
                    updateEmptyState(); isLoading = false
                }
            }
        }
    }

    private fun updateStats() {
        val total = allJobs.size; val showing = filteredJobs.size
        val fuentes = allJobs.map { it.optString("source", "") }.distinct().size
        statsText.text = when {
            getTime() == "recientes" -> "🆕 $showing empleos últ. 2 días"
            getTime() == "semana" -> "📅 $showing empleos últ. semana"
            getSource() != null -> "$showing de $total en ${getSource()}"
            else -> "$showing de $total empleos ($fuentes fuentes)"
        }
    }

    private fun updateEmptyState() {
        emptyContainer.visibility = if (filteredJobs.isEmpty()) View.VISIBLE else View.GONE
        recycler.visibility = if (filteredJobs.isEmpty()) View.GONE else View.VISIBLE
    }

    inner class JobAdapter : RecyclerView.Adapter<JobAdapter.ViewHolder>() {
        override fun onCreateViewHolder(p: ViewGroup, t: Int) = ViewHolder(LayoutInflater.from(p.context).inflate(R.layout.item_job, p, false))
        override fun getItemCount() = filteredJobs.size

        override fun onBindViewHolder(h: ViewHolder, pos: Int) {
            val j = filteredJobs[pos]
            h.title.text = j.optString("title", "Sin título")
            h.company.text = j.optString("company", "Empresa")
            h.location.text = j.optString("location", "Remoto - Global")
            h.categoryIcon.text = when (j.optString("category")) { "junior" -> "🚀"; "pasantia" -> "🎓"; else -> "💼" }
            h.categoryLabel.text = when (j.optString("category")) { "junior" -> "Junior"; "pasantia" -> "Pasantía"; else -> "Remoto" }
            h.source.text = j.optString("source", "Web")
            val posted = j.optString("posted_date", "")
            h.date.text = if (posted.length >= 10) try { SimpleDateFormat("dd MMM", Locale("es")).format(SimpleDateFormat("yyyy-MM-dd", Locale.getDefault()).parse(posted.substring(0, 10))!!) } catch (_: Exception) { "" } else ""
            h.newBadge.visibility = if (j.optBoolean("is_new", false)) View.VISIBLE else View.GONE
            val extra = listOfNotNull(j.optString("salary", "").takeIf { it.isNotEmpty() }, j.optString("tags", "").takeIf { it.isNotEmpty() }).joinToString("  ·  ").take(100)
            if (extra.isNotEmpty()) { h.tags.text = extra; h.tags.visibility = View.VISIBLE } else h.tags.visibility = View.GONE
            val click = { j.optString("url", "").takeIf { it.isNotEmpty() }?.let { try { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(it))) } catch (_: Exception) { Toast.makeText(this@JobsActivity, "No se pudo abrir", Toast.LENGTH_SHORT).show() } } }
            h.btnApply.setOnClickListener { click() }; h.card.setOnClickListener { click() }
        }

        inner class ViewHolder(v: View) : RecyclerView.ViewHolder(v) {
            val card: MaterialCardView = v.findViewById(R.id.card_root)
            val title: TextView = v.findViewById(R.id.job_title)
            val company: TextView = v.findViewById(R.id.job_company)
            val location: TextView = v.findViewById(R.id.job_location)
            val categoryIcon: TextView = v.findViewById(R.id.job_category_icon)
            val categoryLabel: TextView = v.findViewById(R.id.job_category_label)
            val date: TextView = v.findViewById(R.id.job_date)
            val newBadge: TextView = v.findViewById(R.id.job_new_badge)
            val btnApply: TextView = v.findViewById(R.id.btn_apply)
            val source: TextView = v.findViewById(R.id.job_source)
            val tags: TextView = v.findViewById(R.id.job_tags)
        }
    }
}
