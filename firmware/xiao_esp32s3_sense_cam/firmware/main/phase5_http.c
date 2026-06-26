/*
 * Phase 6.1 — HTTP server with redesigned single-page UI.
 *
 * Endpoints:
 *   GET /          rich HTML control page with embedded CSS+JS
 *   GET /stream    multipart/x-mixed-replace MJPEG
 *   GET /snapshot  one-shot image/jpeg
 *   GET /status    JSON {motion, seconds_since_last, event_count, fps,
 *                        free_psram_kb, uptime_s, rssi_dbm, version}
 *
 * The page is fully self-contained — no external CDN, no dependencies.
 * It polls /status every 1 s, drives the on-page status panel, and
 * exposes "pause/resume stream" and "save snapshot" buttons (client-side
 * only — pause hides the <img>, resume restores it; no server load
 * change either way).
 */

#include "phase5_http.h"

#include <inttypes.h>
#include <stdio.h>
#include <string.h>

#include "esp_app_desc.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_http_server.h"
#include "esp_log.h"
#include "esp_system.h"
#include "esp_timer.h"
#include "esp_wifi.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#include "gpio_remap.h"
#include "phase5_cam_pump.h"
#if PHASE5_MOTION_ENABLED
#include "phase5_motion.h"
#endif
#if PHASE6_MQTT_ENABLED
#include "phase6_mqtt.h"
#include "phase6_settings.h"
#endif

static const char *TAG = "sense_http";

#define MJPEG_BOUNDARY    "xframe"
#define COPY_BUF_BYTES    (64u * 1024u)
#define IDLE_POLL_MS      15

/* ---------------- GET / ---------------- */

/* HTML attributes use single quotes throughout so we don't have to escape
 * them inside this C string literal. */
static const char INDEX_HTML[] =
"<!doctype html>"
"<html lang='en'><head>"
"<meta charset='utf-8'>"
"<meta name='viewport' content='width=device-width, initial-scale=1'>"
"<title>XIAO ESP32-S3 Sense</title>"
"<style>"
":root{"
"--bg:#0d1117;--panel:#161b22;--panel2:#21262d;--text:#c9d1d9;--muted:#8b949e;"
"--accent:#58a6ff;--ok:#3fb950;--warn:#d29922;--bad:#f85149;--border:#30363d;"
"}"
"*{box-sizing:border-box}"
"html,body{margin:0;background:var(--bg);color:var(--text);"
"font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}"
"header{background:var(--panel);padding:10px 16px;border-bottom:1px solid var(--border);"
"display:flex;align-items:center;gap:10px;position:sticky;top:0;z-index:10}"
"header .title{font-weight:600}"
"header .meta{color:var(--muted);font-family:ui-monospace,monospace;font-size:12px}"
".dot{display:inline-block;width:10px;height:10px;border-radius:50%;background:var(--muted);"
"transition:background .15s,box-shadow .15s}"
".dot.ok{background:var(--ok);box-shadow:0 0 6px rgba(63,185,80,.5)}"
".dot.bad{background:var(--bad);box-shadow:0 0 6px rgba(248,81,73,.5)}"
".dot.alert{background:var(--bad);animation:pulse 1s infinite}"
"@keyframes pulse{0%,100%{box-shadow:0 0 0 rgba(248,81,73,.7)}"
"50%{box-shadow:0 0 14px rgba(248,81,73,.9)}}"
"main{padding:14px;display:grid;grid-template-columns:1fr 320px;gap:14px;"
"max-width:1400px;margin:0 auto}"
"@media (max-width:880px){main{grid-template-columns:1fr}}"
".video{background:#000;border:1px solid var(--border);border-radius:10px;overflow:hidden;"
"aspect-ratio:4/3;display:flex;align-items:center;justify-content:center;position:relative}"
".video img{width:100%;height:100%;object-fit:contain;display:block}"
".video.paused::after{content:'paused — click resume';color:var(--muted);position:absolute;"
"inset:0;display:grid;place-items:center;font-size:18px;background:#000}"
".panel{background:var(--panel);border:1px solid var(--border);border-radius:10px;"
"padding:12px 14px;margin-bottom:12px}"
".panel h3{margin:0 0 10px 0;font-size:11px;color:var(--muted);"
"text-transform:uppercase;letter-spacing:.08em;font-weight:700}"
".kv{display:grid;grid-template-columns:auto 1fr;gap:6px 14px;"
"font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px}"
".kv .k{color:var(--muted)}"
".kv .v{text-align:right;color:var(--text)}"
".kv .v.alert{color:var(--bad);font-weight:700}"
".kv .v.ok{color:var(--ok)}"
".controls{display:flex;gap:8px;flex-wrap:wrap}"
"button{background:var(--panel2);color:var(--text);border:1px solid var(--border);"
"border-radius:6px;padding:9px 14px;cursor:pointer;font:inherit;transition:all .15s}"
"button:hover{background:var(--accent);border-color:var(--accent);color:#000}"
"button:active{transform:translateY(1px)}"
"select,input[type='range']{background:var(--panel2);color:var(--text);border:1px solid var(--border);"
"border-radius:6px;padding:6px 8px;font:inherit}"
"select{width:100%}"
"input[type='range']{width:100%;padding:0;height:24px}"
"label.ctrl{display:block;margin-bottom:10px;font-size:13px;color:var(--muted)}"
"label.ctrl span{color:var(--text);font-family:ui-monospace,monospace}"
"label.row{display:flex;align-items:center;gap:8px;color:var(--text);cursor:pointer}"
"input[type='checkbox']{accent-color:var(--accent);width:16px;height:16px}"
"footer{color:var(--muted);font-size:12px;text-align:center;padding:18px;opacity:.7}"
"</style>"
"</head><body>"
"<header>"
  "<span class='dot' id='link'></span>"
  "<span class='title'>XIAO ESP32-S3 Sense</span>"
  "<span class='meta' id='hostmeta'></span>"
  "<span style='flex:1'></span>"
  "<span class='meta' id='ver'></span>"
"</header>"
"<main>"
  "<div>"
    "<div class='video' id='vbox'>"
      "<img id='video' alt='live stream'>"
    "</div>"
    "<div class='panel' style='margin-top:12px'>"
      "<h3>Stream controls</h3>"
      "<div class='controls'>"
        "<button id='pause'>Pause stream</button>"
        "<button id='snap'>Save snapshot</button>"
        "<button id='reload'>Reload stream</button>"
      "</div>"
    "</div>"
    "<div class='panel'>"
      "<h3>Camera</h3>"
      "<label class='ctrl'>Frame size"
        "<select id='framesize'>"
          "<option value='QQVGA'>QQVGA &mdash; 160&times;120</option>"
          "<option value='QVGA'>QVGA &mdash; 320&times;240</option>"
          "<option value='CIF'>CIF &mdash; 400&times;296</option>"
        "</select>"
        "<small style='color:var(--muted)'>"
        "VGA+ disabled (camera FB-OVF without PSRAM-DMA mode \xe2\x80\x94 see Phase 7 backlog)"
        "</small>"
      "</label>"
      "<label class='ctrl'>JPEG quality &mdash; <span id='quality-val'>?</span> "
        "<small>(lower &rarr; higher quality, 6 &ndash; 30)</small>"
        "<input type='range' min='6' max='30' id='quality' step='1'>"
      "</label>"
    "</div>"
  "</div>"
  "<aside>"
    "<div class='panel'>"
      "<h3>Motion</h3>"
      "<div class='kv'>"
        "<span class='k'>state</span><span class='v' id='motion'>\xe2\x80\xa6</span>"
        "<span class='k'>last seen</span><span class='v' id='since'>\xe2\x80\xa6</span>"
        "<span class='k'>events</span><span class='v' id='events'>\xe2\x80\xa6</span>"
      "</div>"
      "<div style='margin-top:10px'>"
        "<label class='row'><input type='checkbox' id='motion-toggle'>"
        "<span>detection enabled</span></label>"
      "</div>"
    "</div>"
    "<div class='panel' id='mqtt-panel'>"
      "<h3>MQTT</h3>"
      "<label class='ctrl'>Broker URI"
        "<input type='text' id='mqtt-uri' placeholder='mqtt://10.10.8.140:1883' autocomplete='off'>"
      "</label>"
      "<label class='ctrl'>Topic"
        "<input type='text' id='mqtt-topic' autocomplete='off'>"
      "</label>"
      "<label class='ctrl'>Username"
        "<input type='text' id='mqtt-user' autocomplete='off'>"
      "</label>"
      "<label class='ctrl'>Password"
        "<input type='password' id='mqtt-pass' autocomplete='new-password'>"
      "</label>"
      "<label class='ctrl'>QoS"
        "<select id='mqtt-qos'>"
          "<option value='0'>0 \xe2\x80\x94 at most once</option>"
          "<option value='1'>1 \xe2\x80\x94 at least once</option>"
          "<option value='2'>2 \xe2\x80\x94 exactly once</option>"
        "</select>"
      "</label>"
      "<label class='row'><input type='checkbox' id='mqtt-retain'><span>retain</span></label>"
      "<label class='row' style='margin-top:6px'>"
        "<input type='checkbox' id='mqtt-enabled'><span>enabled</span></label>"
      "<div class='controls' style='margin-top:10px'>"
        "<button id='mqtt-save'>Save &amp; connect</button>"
        "<button id='mqtt-test'>Test publish</button>"
      "</div>"
      "<div class='kv' style='margin-top:10px'>"
        "<span class='k'>state</span>"
        "<span class='v'><span class='dot' id='mqtt-dot' style='vertical-align:middle'></span> "
        "<span id='mqtt-state'>\xe2\x80\xa6</span></span>"
        "<span class='k'>publishes</span><span class='v' id='mqtt-pubs'>\xe2\x80\xa6</span>"
      "</div>"
    "</div>"
    "<div class='panel'>"
      "<h3>System</h3>"
      "<div class='kv'>"
        "<span class='k'>camera fps</span><span class='v' id='fps'>\xe2\x80\xa6</span>"
        "<span class='k'>free PSRAM</span><span class='v' id='psram'>\xe2\x80\xa6</span>"
        "<span class='k'>RSSI</span><span class='v' id='rssi'>\xe2\x80\xa6</span>"
        "<span class='k'>uptime</span><span class='v' id='uptime'>\xe2\x80\xa6</span>"
      "</div>"
    "</div>"
  "</aside>"
"</main>"
"<footer>XIAO ESP32-S3 Sense \xc2\xb7 Phase 6.1 \xc2\xb7 self-contained UI</footer>"
"<script>"
"const $=id=>document.getElementById(id);"
"const f=(n,d)=>(typeof n==='number'&&isFinite(n))?n.toFixed(d==null?2:d):'-';"
"const fmtAge=s=>{if(s<0)return'never';if(s<60)return f(s,1)+' s';"
"if(s<3600)return Math.floor(s/60)+' m '+Math.round(s%60)+' s';"
"return Math.floor(s/3600)+' h '+Math.floor((s%3600)/60)+' m'};"
"$('hostmeta').textContent=location.host;"
"const STREAM_BASE='http://'+location.hostname+':81';"
"function streamUrl(){return STREAM_BASE+'/stream?ts='+Date.now()}"
"$('video').src=streamUrl();"
"let paused=false;"
"$('pause').onclick=()=>{paused=!paused;const v=$('video'),b=$('vbox');"
"if(paused){v.removeAttribute('src');b.classList.add('paused');"
"$('pause').textContent='Resume stream'}"
"else{v.src=streamUrl();b.classList.remove('paused');"
"$('pause').textContent='Pause stream'}};"
"$('snap').onclick=()=>{const a=document.createElement('a');"
"const ts=new Date().toISOString().replace(/[:.]/g,'-').replace(/Z$/,'');"
"a.href='/snapshot?ts='+Date.now();a.download='xiao-snap-'+ts+'.jpg';"
"document.body.appendChild(a);a.click();a.remove()};"
"$('reload').onclick=()=>{$('video').src=streamUrl()};"
"async function ctl(params){"
"const q=new URLSearchParams(params).toString();"
"try{const r=await fetch('/control?'+q,{method:'POST',cache:'no-store'});"
"if(r.ok){const j=await r.json();update(j)}}"
"catch(e){console.warn('ctl failed',e)}"
"}"
"$('framesize').addEventListener('change',e=>{"
"const v=$('video');v.removeAttribute('src');"
"setTimeout(()=>{v.src='/stream?ts='+Date.now()},800);"
"ctl({framesize:e.target.value})});"
"let qDeb;"
"$('quality').addEventListener('input',e=>{$('quality-val').textContent=e.target.value;"
"clearTimeout(qDeb);qDeb=setTimeout(()=>ctl({quality:e.target.value}),200)});"
"$('motion-toggle').addEventListener('change',e=>"
"ctl({motion:e.target.checked?'on':'off'}));"
"$('mqtt-save').onclick=()=>ctl({"
"mqtt_uri:$('mqtt-uri').value,"
"mqtt_topic:$('mqtt-topic').value,"
"mqtt_user:$('mqtt-user').value,"
"mqtt_pass:$('mqtt-pass').value,"
"mqtt_qos:$('mqtt-qos').value,"
"mqtt_retain:$('mqtt-retain').checked?'1':'0',"
"mqtt_enabled:$('mqtt-enabled').checked?'1':'0'"
"});"
"$('mqtt-test').onclick=async()=>{"
"try{const r=await fetch('/mqtt-test',{method:'POST',cache:'no-store'});"
"const j=await r.json();"
"$('mqtt-test').textContent=j.ok?'Published \xe2\x9c\x93':'Failed: '+(j.err||'');"
"setTimeout(()=>{$('mqtt-test').textContent='Test publish'},2000)}"
"catch(e){$('mqtt-test').textContent='Network error';"
"setTimeout(()=>{$('mqtt-test').textContent='Test publish'},2000)}"
"};"
"let synced=false;"
"function update(j){"
"const m=$('motion');"
"if(j.motion){m.textContent='ACTIVE';m.className='v alert';$('link').className='dot alert'}"
"else{m.textContent=(j.motion_enabled===false?'disabled':'idle');"
"m.className=(j.motion_enabled===false?'v':'v ok');"
"$('link').className='dot ok'}"
"$('since').textContent=fmtAge(j.seconds_since_last);"
"$('events').textContent=j.event_count;"
"$('fps').textContent=f(j.fps,1);"
"$('psram').textContent=j.free_psram_kb+' kB';"
"$('rssi').textContent=(j.rssi_dbm!=null?j.rssi_dbm+' dBm':'-');"
"$('uptime').textContent=fmtAge(j.uptime_s);"
"if(j.version)$('ver').textContent=j.version;"
"if(j.mqtt_state){"
"$('mqtt-state').textContent=j.mqtt_state;"
"const md=$('mqtt-dot');"
"md.className='dot '+(j.mqtt_state==='connected'?'ok':"
"(j.mqtt_state==='disabled'?'':'bad'));"
"}"
"if(j.mqtt_publish_count!=null)$('mqtt-pubs').textContent=j.mqtt_publish_count;"
"if(!synced){"
"if(j.framesize)$('framesize').value=j.framesize;"
"if(j.quality!=null){$('quality').value=j.quality;$('quality-val').textContent=j.quality}"
"if(j.motion_enabled!=null)$('motion-toggle').checked=j.motion_enabled;"
"if(j.mqtt_uri!=null)$('mqtt-uri').value=j.mqtt_uri;"
"if(j.mqtt_topic!=null)$('mqtt-topic').value=j.mqtt_topic;"
"if(j.mqtt_user!=null)$('mqtt-user').value=j.mqtt_user;"
"if(j.mqtt_qos!=null)$('mqtt-qos').value=j.mqtt_qos;"
"if(j.mqtt_retain!=null)$('mqtt-retain').checked=j.mqtt_retain;"
"if(j.mqtt_enabled!=null)$('mqtt-enabled').checked=j.mqtt_enabled;"
"synced=true}"
"}"
"async function poll(){"
"try{const r=await fetch('/status',{cache:'no-store'});"
"if(!r.ok)throw 0;const j=await r.json();update(j);"
"}catch(e){$('link').className='dot bad'}"
"}"
"poll();setInterval(poll,1000);"
"</script>"
"</body></html>";

static esp_err_t index_handler(httpd_req_t *req)
{
    httpd_resp_set_type(req, "text/html; charset=utf-8");
    httpd_resp_set_hdr(req, "Cache-Control", "no-cache");
    return httpd_resp_send(req, INDEX_HTML, sizeof(INDEX_HTML) - 1);
}

/* ---------------- GET /snapshot ---------------- */

static esp_err_t snapshot_handler(httpd_req_t *req)
{
    uint8_t *buf = heap_caps_malloc(COPY_BUF_BYTES, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "no memory");
        return ESP_FAIL;
    }
    size_t   len = 0;
    uint32_t seq = 0;
    esp_err_t err = phase5_cam_pump_copy_latest(buf, COPY_BUF_BYTES, &len, &seq);
    if (err != ESP_OK) {
        free(buf);
        httpd_resp_send_err(req, HTTPD_404_NOT_FOUND,
                            err == ESP_ERR_NOT_FOUND ? "no frame yet"
                                                     : "frame too big");
        return ESP_FAIL;
    }
    httpd_resp_set_type(req, "image/jpeg");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    esp_err_t r = httpd_resp_send(req, (const char *)buf, len);
    free(buf);
    return r;
}

/* ---------------- GET /stream ---------------- */

static esp_err_t stream_handler(httpd_req_t *req)
{
    uint8_t *buf = heap_caps_malloc(COPY_BUF_BYTES, MALLOC_CAP_SPIRAM);
    if (buf == NULL) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "no memory");
        return ESP_FAIL;
    }
    char part_hdr[96];

    esp_err_t err = httpd_resp_set_type(req,
        "multipart/x-mixed-replace;boundary=" MJPEG_BOUNDARY);
    if (err != ESP_OK) {
        free(buf);
        return err;
    }
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "X-Frame-Options", "DENY");

    ESP_LOGI(TAG, "stream client connected");

    uint32_t last_seq = 0;
    int      sent     = 0;
    int64_t  t0       = esp_timer_get_time();

    while (true) {
        size_t   len = 0;
        uint32_t seq = 0;
        esp_err_t cr = phase5_cam_pump_copy_latest(buf, COPY_BUF_BYTES, &len, &seq);
        if (cr != ESP_OK || seq == last_seq) {
            vTaskDelay(pdMS_TO_TICKS(IDLE_POLL_MS));
            continue;
        }
        last_seq = seq;

        int n = snprintf(part_hdr, sizeof(part_hdr),
            "\r\n--" MJPEG_BOUNDARY "\r\n"
            "Content-Type: image/jpeg\r\n"
            "Content-Length: %u\r\n\r\n",
            (unsigned)len);
        if (httpd_resp_send_chunk(req, part_hdr, n) != ESP_OK) break;
        if (httpd_resp_send_chunk(req, (const char *)buf, len) != ESP_OK) break;
        sent++;
    }

    int64_t dt = esp_timer_get_time() - t0;
    ESP_LOGI(TAG, "stream client done: %d frames in %" PRId64 " ms (%.1f fps)",
             sent, dt / 1000,
             dt > 0 ? (float)sent * 1e6f / (float)dt : 0.0f);

    /* server-side stream end: empty chunk */
    (void)httpd_resp_send_chunk(req, NULL, 0);
    free(buf);
    return ESP_OK;
}

/* ---------------- GET /status ---------------- */

#if PHASE5_MOTION_ENABLED
/* Map the last reset cause to a short token so the reboot reason is visible
 * over HTTP (it is otherwise only on the serial console). "BROWNOUT" here
 * confirms a power-sag reset; "PANIC"/"*_WDT" point at firmware instead. */
static const char *reset_reason_name(esp_reset_reason_t r)
{
    switch (r) {
    case ESP_RST_POWERON:   return "POWERON";
    case ESP_RST_EXT:       return "EXT";
    case ESP_RST_SW:        return "SW";
    case ESP_RST_PANIC:     return "PANIC";
    case ESP_RST_INT_WDT:   return "INT_WDT";
    case ESP_RST_TASK_WDT:  return "TASK_WDT";
    case ESP_RST_WDT:       return "WDT";
    case ESP_RST_DEEPSLEEP: return "DEEPSLEEP";
    case ESP_RST_BROWNOUT:  return "BROWNOUT";
    case ESP_RST_SDIO:      return "SDIO";
    case ESP_RST_USB:       return "USB";
    case ESP_RST_JTAG:      return "JTAG";
    default:                return "UNKNOWN";
    }
}

static esp_err_t status_handler(httpd_req_t *req)
{
    char json[544];

    bool     m     = phase5_motion_is_active();
    bool     m_en  = phase5_motion_get_enabled();
    float    since = phase5_motion_seconds_since_last();
    uint32_t evts  = phase5_motion_event_count();
    float    fps   = phase5_cam_pump_fps();
    int      psram_kb = (int)(heap_caps_get_free_size(MALLOC_CAP_SPIRAM) / 1024);
    int      heap_kb  = (int)(heap_caps_get_free_size(MALLOC_CAP_INTERNAL) / 1024);
    int      uptime_s = (int)(esp_timer_get_time() / 1000000);
    const char *reset_reason = reset_reason_name(esp_reset_reason());

    const char *fs_name = phase5_cam_pump_get_framesize_name();
    int         quality = phase5_cam_pump_get_quality();

    /* RSSI: cheap if associated, ESP_ERR_WIFI_NOT_CONNECT otherwise. */
    int rssi_dbm = 127;       /* sentinel */
    wifi_ap_record_t ap = { 0 };
    if (esp_wifi_sta_get_ap_info(&ap) == ESP_OK) {
        rssi_dbm = ap.rssi;
    }

    /* Version string from the IDF app description (git-derived). */
    const esp_app_desc_t *desc = esp_app_get_description();
    const char *version = (desc && desc->version[0]) ? desc->version : "unknown";

#if PHASE6_MQTT_ENABLED
    /* Pull MQTT settings + live state for the UI to render. Note: we
     * never include the password in /status. */
    char mqtt_uri  [160] = { 0 };
    char mqtt_topic[128] = { 0 };
    char mqtt_user [64]  = { 0 };
    phase6_settings_get_str("mqtt_uri",   mqtt_uri,   sizeof(mqtt_uri),   "");
    phase6_settings_get_str("mqtt_topic", mqtt_topic, sizeof(mqtt_topic), "siot/xiao-esp32s3-sense/motion");
    phase6_settings_get_str("mqtt_user",  mqtt_user,  sizeof(mqtt_user),  "");
    int  mqtt_qos     = phase6_settings_get_int ("mqtt_qos",    0);
    bool mqtt_retain  = phase6_settings_get_bool("mqtt_retain", false);
    bool mqtt_enabled = phase6_settings_get_bool("mqtt_en",     false);
    const char *mqtt_state    = phase6_mqtt_state_name();
    uint32_t    mqtt_pub_cnt  = phase6_mqtt_publish_count();
#endif

    int n = snprintf(json, sizeof(json),
        "{\"motion\":%s,\"motion_enabled\":%s,"
        "\"seconds_since_last\":%.2f,"
        "\"event_count\":%u,\"fps\":%.1f,\"free_psram_kb\":%d,"
        "\"uptime_s\":%d,\"rssi_dbm\":%d,"
        "\"reset_reason\":\"%s\",\"free_heap_kb\":%d,"
        "\"framesize\":\"%s\",\"quality\":%d,"
#if PHASE6_MQTT_ENABLED
        "\"mqtt_enabled\":%s,\"mqtt_state\":\"%s\","
        "\"mqtt_uri\":\"%.95s\",\"mqtt_topic\":\"%.95s\","
        "\"mqtt_user\":\"%.31s\","
        "\"mqtt_qos\":%d,\"mqtt_retain\":%s,"
        "\"mqtt_publish_count\":%u,"
#endif
        "\"version\":\"%.31s\"}",
        m    ? "true" : "false",
        m_en ? "true" : "false",
        (double)since, (unsigned)evts, (double)fps, psram_kb,
        uptime_s, rssi_dbm, reset_reason, heap_kb, fs_name, quality,
#if PHASE6_MQTT_ENABLED
        mqtt_enabled ? "true" : "false", mqtt_state,
        mqtt_uri, mqtt_topic, mqtt_user,
        mqtt_qos, mqtt_retain ? "true" : "false",
        (unsigned)mqtt_pub_cnt,
#endif
        version);

    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    return httpd_resp_send(req, json, n);
}
#endif

/* ---------------- POST /control ---------------- *
 *
 * Accepts URL-query params (works whether the client sends GET or POST):
 *   framesize=<NAME>     (QQVGA|QVGA|CIF|VGA|SVGA|XGA|HD|UXGA)
 *   quality=<int 6..30>  (lower = higher JPEG quality)
 *   motion=<on|off>      (1/true/yes also accepted)
 *
 * Returns the same JSON shape as /status. Unknown values are skipped
 * with a warning log; valid values are queued for the cam_pump task
 * (frame-size requires deinit+reinit; quality is hot-tweaked).
 */
#if PHASE5_MOTION_ENABLED

static bool parse_bool_on(const char *s)
{
    return strcmp(s, "on")   == 0
        || strcmp(s, "1")    == 0
        || strcmp(s, "true") == 0
        || strcmp(s, "yes")  == 0;
}

/* In-place URL-decode. esp_http_server's httpd_query_key_value returns
 * the raw percent-encoded value, so anything with /, :, &, =, +, or
 * non-ASCII needs cleaning before storage or downstream use. */
static void url_decode_inplace(char *s)
{
    if (s == NULL) return;
    char *r = s;
    char *w = s;
    while (*r != '\0') {
        if (r[0] == '%' && r[1] != '\0' && r[2] != '\0') {
            char h1 = r[1], h2 = r[2];
            int hi = (h1 >= '0' && h1 <= '9') ? h1 - '0'
                   : (h1 >= 'A' && h1 <= 'F') ? h1 - 'A' + 10
                   : (h1 >= 'a' && h1 <= 'f') ? h1 - 'a' + 10
                   : -1;
            int lo = (h2 >= '0' && h2 <= '9') ? h2 - '0'
                   : (h2 >= 'A' && h2 <= 'F') ? h2 - 'A' + 10
                   : (h2 >= 'a' && h2 <= 'f') ? h2 - 'a' + 10
                   : -1;
            if (hi >= 0 && lo >= 0) {
                *w++ = (char)((hi << 4) | lo);
                r += 3;
                continue;
            }
        }
        if (*r == '+') {
            *w++ = ' ';
            r++;
            continue;
        }
        *w++ = *r++;
    }
    *w = '\0';
}

static esp_err_t control_handler(httpd_req_t *req)
{
    /* Larger query buffer than 6.2 — MQTT URI + creds add up. */
    char query[640];
    char val[256];
    int  applied = 0;
#if PHASE6_MQTT_ENABLED
    bool mqtt_dirty = false;
#endif

    if (httpd_req_get_url_query_str(req, query, sizeof(query)) == ESP_OK) {
        if (httpd_query_key_value(query, "framesize", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            esp_err_t e = phase5_cam_pump_request_framesize(val);
            if (e == ESP_OK) {
                applied++;
#if PHASE6_MQTT_ENABLED
                phase6_settings_set_str("cam_fs", val);
#endif
            } else {
                ESP_LOGW(TAG, "control: framesize='%s' rejected: 0x%x", val, e);
            }
        }
        if (httpd_query_key_value(query, "quality", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            int q = atoi(val);
            esp_err_t e = phase5_cam_pump_request_quality(q);
            if (e == ESP_OK) {
                applied++;
#if PHASE6_MQTT_ENABLED
                phase6_settings_set_int("cam_q", q);
#endif
            } else {
                ESP_LOGW(TAG, "control: quality='%s' (%d) rejected: 0x%x", val, q, e);
            }
        }
        if (httpd_query_key_value(query, "motion", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            bool e = parse_bool_on(val);
            phase5_motion_set_enabled(e);
            applied++;
#if PHASE6_MQTT_ENABLED
            phase6_settings_set_bool("motion_en", e);
#endif
        }
#if PHASE6_MQTT_ENABLED
        if (httpd_query_key_value(query, "mqtt_uri", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_str("mqtt_uri", val);
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_topic", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_str("mqtt_topic", val);
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_user", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_str("mqtt_user", val);
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_pass", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_str("mqtt_pass", val);
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_qos", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            int qos = atoi(val);
            if (qos < 0) qos = 0;
            if (qos > 2) qos = 2;
            phase6_settings_set_int("mqtt_qos", qos);
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_retain", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_bool("mqtt_retain", parse_bool_on(val));
            mqtt_dirty = true; applied++;
        }
        if (httpd_query_key_value(query, "mqtt_enabled", val, sizeof(val)) == ESP_OK) {
            url_decode_inplace(val);
            phase6_settings_set_bool("mqtt_en", parse_bool_on(val));
            mqtt_dirty = true; applied++;
        }

        if (mqtt_dirty) {
            /* Re-read everything from NVS and (re)apply. The disconnect
             * + reconnect path lives entirely inside phase6_mqtt. */
            char uri[160], user[64], pass[64], topic[128];
            phase6_settings_get_str("mqtt_uri",   uri,   sizeof(uri),   "");
            phase6_settings_get_str("mqtt_user",  user,  sizeof(user),  "");
            phase6_settings_get_str("mqtt_pass",  pass,  sizeof(pass),  "");
            phase6_settings_get_str("mqtt_topic", topic, sizeof(topic),
                                    "siot/xiao-esp32s3-sense/motion");
            int  qos     = phase6_settings_get_int ("mqtt_qos",    0);
            bool retain  = phase6_settings_get_bool("mqtt_retain", false);
            bool enabled = phase6_settings_get_bool("mqtt_en",     false);
            (void)phase6_mqtt_apply_config(uri, user, pass, topic, qos, retain, enabled);
        }
#endif
    }

    ESP_LOGI(TAG, "control applied=%d", applied);

    /* Reuse status_handler's JSON formatter so clients can rely on a
     * single response shape across /status and /control. */
    return status_handler(req);
}

#if PHASE6_MQTT_ENABLED
static esp_err_t mqtt_test_handler(httpd_req_t *req)
{
    esp_err_t err = phase6_mqtt_publish_test();
    httpd_resp_set_type(req, "application/json");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    if (err == ESP_OK) {
        return httpd_resp_send(req, "{\"ok\":true}", 11);
    }
    char body[80];
    int n = snprintf(body, sizeof(body),
        "{\"ok\":false,\"err\":\"%s\"}", esp_err_to_name(err));
    return httpd_resp_send(req, body, n);
}
#endif

#endif

/* ---------------- Bring-up ---------------- */

/* Two httpd instances:
 *   :80 — control plane: short-lived requests (index, status, control,
 *         snapshot, mqtt-test). Worker task returns quickly so polling
 *         from the browser stays responsive.
 *   :81 — data plane:    long-lived /stream MJPEG. Its worker task is
 *         pinned in `while(1) httpd_resp_send_chunk()` for the lifetime
 *         of each client; isolating it here means it can't starve the
 *         control plane.
 *
 * The browser requests /stream with an absolute URL `http://<host>:81/stream`
 * (built in JS from location.hostname); same-origin policy is permissive
 * for <img> elements so this works without CORS plumbing.
 */
esp_err_t phase5_http_start(void)
{
    /* ---- Control plane on :80 ---- */
    httpd_config_t cfg_ctl = HTTPD_DEFAULT_CONFIG();
    cfg_ctl.server_port      = 80;
    cfg_ctl.ctrl_port        = 32768;
    cfg_ctl.max_uri_handlers = 8;
    cfg_ctl.stack_size       = 8 * 1024;
    cfg_ctl.max_open_sockets = 7;
    cfg_ctl.lru_purge_enable = true;

    httpd_handle_t server_ctl = NULL;
    esp_err_t err = httpd_start(&server_ctl, &cfg_ctl);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start :80 failed: 0x%x (%s)", err, esp_err_to_name(err));
        return err;
    }

    static const httpd_uri_t uri_index    = {.uri="/",         .method=HTTP_GET, .handler=index_handler};
    static const httpd_uri_t uri_snapshot = {.uri="/snapshot", .method=HTTP_GET, .handler=snapshot_handler};
    httpd_register_uri_handler(server_ctl, &uri_index);
    httpd_register_uri_handler(server_ctl, &uri_snapshot);

#if PHASE5_MOTION_ENABLED
    static const httpd_uri_t uri_status      = {.uri="/status",  .method=HTTP_GET,  .handler=status_handler};
    static const httpd_uri_t uri_control_get = {.uri="/control", .method=HTTP_GET,  .handler=control_handler};
    static const httpd_uri_t uri_control_pst = {.uri="/control", .method=HTTP_POST, .handler=control_handler};
    httpd_register_uri_handler(server_ctl, &uri_status);
    httpd_register_uri_handler(server_ctl, &uri_control_get);
    httpd_register_uri_handler(server_ctl, &uri_control_pst);
#if PHASE6_MQTT_ENABLED
    static const httpd_uri_t uri_mqtt_test = {.uri="/mqtt-test", .method=HTTP_POST, .handler=mqtt_test_handler};
    httpd_register_uri_handler(server_ctl, &uri_mqtt_test);
#endif
#endif

    /* ---- Data plane on :81 ---- */
    httpd_config_t cfg_str = HTTPD_DEFAULT_CONFIG();
    cfg_str.server_port      = 81;
    cfg_str.ctrl_port        = 32769;
    cfg_str.max_uri_handlers = 2;
    cfg_str.stack_size       = 8 * 1024;
    cfg_str.max_open_sockets = 4;          /* 1-3 concurrent stream clients */
    cfg_str.lru_purge_enable = true;

    httpd_handle_t server_str = NULL;
    err = httpd_start(&server_str, &cfg_str);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "httpd_start :81 failed: 0x%x (%s)", err, esp_err_to_name(err));
        return err;
    }
    static const httpd_uri_t uri_stream = {.uri="/stream", .method=HTTP_GET, .handler=stream_handler};
    httpd_register_uri_handler(server_str, &uri_stream);

    ESP_LOGI(TAG, "control plane on :80, data plane (/stream) on :81");
    return ESP_OK;
}
