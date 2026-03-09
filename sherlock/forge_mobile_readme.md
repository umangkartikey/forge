# FORGE MOBILE — Setup Guide

## What it does
FORGE in your pocket. Run on Android (Termux), iOS (a-Shell), or any desktop.

## Quick Start (Android/Termux)
```bash
pkg install python termux-api
pip install anthropic requests pillow qrcode
python forge_mobile.py --server
```
Then open the URL shown on your phone browser. Install as PWA from browser menu.

## Modules

### 📍 GPS
```bash
python forge_mobile.py --gps
```
- Termux API (real GPS on Android)
- IP geolocation fallback
- Geofence triggers
- Route history

### 📸 Photo Analysis  
```bash
python forge_mobile.py --photo suspect.jpg --alibi "I was in London"
```
- Sherlock visual analysis
- GeoSpy location (needs API key)
- Alibi contradiction check

### 🔔 Push Alerts (ntfy.sh — free, no account)
```bash
python forge_mobile.py --push "Target spotted"
```
Subscribe at: https://ntfy.sh/{your_topic}
Auto-generated topic in config.

### 📲 SMS Interface (Termux only)
Text your phone: `forge osint example.com`
FORGE replies via SMS automatically.

### 📶 Network Scanner
```bash
python forge_mobile.py --scan
```
WiFi networks, device discovery, rogue AP detection.

## Server + PWA
```bash
python forge_mobile.py --server
```
- Opens on http://your-ip:7345
- Installable PWA (Add to Home Screen)
- Photo upload + analysis
- Live GPS
- Push alerts
- Network scan

## API Endpoints
```
GET  /api/status           System status
GET  /api/gps/location     Current GPS
GET  /api/gps/route        Today's route
POST /api/photo/analyze    Analyze image (base64)
POST /api/intel/quick      Quick OSINT
POST /api/alerts/send      Send push notification
POST /api/network/scan     Scan network
POST /api/sms/process      Process SMS command
```

## The Killer Workflow
1. See something suspicious
2. Snap photo on phone
3. Open FORGE PWA
4. Upload photo
5. Add context/alibi
6. Get full Sherlock + GeoSpy analysis in 15s
