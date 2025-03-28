#include "esp_camera.h"
#include <WiFi.h>
#include <esp_http_server.h>
#include <ArduinoJson.h>

// Camera Pin Config
#define PWDN_GPIO_NUM     -1
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     21
#define SIOD_GPIO_NUM     26
#define SIOC_GPIO_NUM     27
#define Y9_GPIO_NUM       35
#define Y8_GPIO_NUM       34
#define Y7_GPIO_NUM       39
#define Y6_GPIO_NUM       36
#define Y5_GPIO_NUM       19
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       5
#define Y2_GPIO_NUM       4
#define VSYNC_GPIO_NUM    25
#define HREF_GPIO_NUM     23
#define PCLK_GPIO_NUM     22

// WiFi Credentials
const char* ssid = "********";
const char* password = "**********";

#define STREAM_CONTENT_TYPE "multipart/x-mixed-replace;boundary=frame"
#define STREAM_BOUNDARY "\r\n--frame\r\n"

// Stream Handler (unchanged)
esp_err_t stream_handler(httpd_req_t *req) {
  camera_fb_t *fb = NULL;
  esp_err_t res = ESP_OK;
  size_t _jpg_buf_len = 0;
  uint8_t *_jpg_buf = NULL;

  res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
  if (res != ESP_OK) return res;

  httpd_resp_set_hdr(req, "Connection", "close");

  while (true) {
    fb = esp_camera_fb_get();
    if (!fb) {
      Serial.println("Camera capture failed");
      delay(50);
      continue;
    }

    if (fb->format != PIXFORMAT_JPEG) {
      if (!frame2jpg(fb, 80, &_jpg_buf, &_jpg_buf_len)) {
        Serial.println("JPEG compression failed");
        esp_camera_fb_return(fb);
        continue;
      }
      esp_camera_fb_return(fb);
    } else {
      _jpg_buf_len = fb->len;
      _jpg_buf = fb->buf;
    }

    char header[64];
    size_t header_len = snprintf(header, sizeof(header), 
      "%sContent-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n", 
      STREAM_BOUNDARY, _jpg_buf_len);

    res = httpd_resp_send_chunk(req, header, header_len);
    if (res == ESP_OK) {
      res = httpd_resp_send_chunk(req, (const char *)_jpg_buf, _jpg_buf_len);
    }

    if (fb->format != PIXFORMAT_JPEG) free(_jpg_buf);
    else esp_camera_fb_return(fb);

    if (res != ESP_OK) {
      Serial.println("Stream error");
      break;
    }
    taskYIELD();
  }
  return res;
}

// Movement Handler
esp_err_t movement_handler(httpd_req_t *req) {
  char content[100];
  size_t recv_size = min(req->content_len, sizeof(content) - 1);

  int ret = httpd_req_recv(req, content, recv_size);
  if (ret <= 0) {
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Failed to receive data");
    return ESP_FAIL;
  }
  content[ret] = '\0';

  StaticJsonDocument<200> doc;
  DeserializationError error = deserializeJson(doc, content);
  if (error) {
    Serial.printf("JSON parse error: %s\n", error.c_str());
    httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
    return ESP_FAIL;
  }

  float delta_x_cm = doc["delta_x_cm"] | 0.0;
  float delta_y_cm = doc["delta_y_cm"] | 0.0;

  Serial.printf("Received movement: delta_x_cm=%.1f, delta_y_cm=%.1f\n", delta_x_cm, delta_y_cm);

  // Send via Serial (GPIO 1 TX) to Nano 33 BLE
  char serialData[50];
  snprintf(serialData, sizeof(serialData), "%.1f,%.1f\n", delta_x_cm, delta_y_cm);
  Serial.print(serialData);  // Send via GPIO 1 TX

  const char* resp = "Movement command received";
  httpd_resp_send(req, resp, strlen(resp));
  return ESP_OK;
}

// Start Server
void startServer() {
  httpd_config_t config = HTTPD_DEFAULT_CONFIG();
  config.server_port = 80;
  config.ctrl_port = 32768;
  config.max_open_sockets = 4;
  config.stack_size = 4096;
  config.task_priority = 5;

  httpd_handle_t server = NULL;
  if (httpd_start(&server, &config) == ESP_OK) {
    httpd_uri_t uri_stream = {
      .uri       = "/stream",
      .method    = HTTP_GET,
      .handler   = stream_handler,
      .user_ctx  = NULL
    };
    httpd_uri_t uri_move = {
      .uri       = "/move",
      .method    = HTTP_POST,
      .handler   = movement_handler,
      .user_ctx  = NULL
    };
    
    httpd_register_uri_handler(server, &uri_stream);
    httpd_register_uri_handler(server, &uri_move);
    Serial.println("✅ Server started");
  } else {
    Serial.println("❌ Failed to start server");
  }
}

// Setup
void setup() {
  Serial.begin(115200);  // Serial communication on GPIO 1 (TX) for both debugging and Nano
  Serial.setDebugOutput(false);

  // Camera setup
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 10000000;
  config.pixel_format = PIXFORMAT_JPEG;
  config.frame_size   = FRAMESIZE_VGA;
  config.jpeg_quality = 10;
  config.fb_count     = 2;
  config.fb_location  = CAMERA_FB_IN_PSRAM;
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("❌ Camera init failed with error: %s\n", esp_err_to_name(err));
    while (true) delay(1000);
  }

  sensor_t *s = esp_camera_sensor_get();
  if (s != NULL) {
    s->set_brightness(s, 2);
    s->set_contrast(s, 1);
    s->set_saturation(s, 0);
  }
  Serial.println("✅ Camera initialized");

  // WiFi setup
  WiFi.begin(ssid, password);
  WiFi.setSleep(false);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\n✅ WiFi connected");
  Serial.print("🌐 Stream at: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/stream");
  Serial.print("🎮 Move at: http://");
  Serial.print(WiFi.localIP());
  Serial.println("/move");

  startServer();
}

// Loop
void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, attempting to reconnect...");
    WiFi.reconnect();
    while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
    }
    Serial.println("\n✅ WiFi reconnected");
    startServer();
  }
  delay(10000);
}
