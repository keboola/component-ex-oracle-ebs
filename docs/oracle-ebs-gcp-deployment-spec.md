# Oracle E-Business Suite 12.2.15 - Deployment Specification for Google Cloud Platform

## Purpose

Deploy Oracle E-Business Suite (EBS) 12.2.15 with Vision Demo data on a Google Cloud Platform Compute Engine VM. The goal is to have a fully functional EBS testing environment for developing Keboola extractors and writers against EBS APIs and database.

## Context

- Keboola Czech s.r.o. is an approved Oracle Partner (OPN Level 1, Company ID: 4-822617251139)
- **License & Hardware Path enrollment: VERIFIED** (Subscription ID: 1624390, Status: Approved, Active: Y, valid 27-FEB-2026 to 27-JAN-2027)
- EBS software is downloadable from Oracle Software Delivery Cloud (edelivery.oracle.com) under account component.factory@keboola.com
- The OCI Marketplace pre-built image is NOT usable on GCP - manual installation via Rapid Install is required

---

## Step 1: Download EBS Installation Media (MANUAL - Human Required)

Log in to https://edelivery.oracle.com with credentials for component.factory@keboola.com.

Search for **"Oracle E-Business Suite 12.2.15"** (DLP package). Select it and choose platform **Linux x86-64** for all components.

### Files to download (VERIFIED from edelivery.oracle.com):

| Component | Platform | Size | Required? |
|-----------|----------|------|-----------|
| **Oracle E-Business Suite 12.2.0 Current** | Linux x86-64 | **31.7 GB** | YES - base install + Vision Demo data |
| **Oracle E-Business Suite 12.2.15** | Linux x86-64 | **39.3 GB** | YES - latest patches |
| **Oracle Database 19.3.0.0.0 - Long Term Release** | Linux x86-64 | (select platform) | YES - database engine |
| **Oracle Web Tier 11.1.1.9.0** | Linux x86-64 | **2.0 GB** | YES - web server |
| **Oracle WebLogic Server 10.3.6.0.0** | Linux x86-64 | **1018.5 MB** | YES - application server |
| Oracle E-Business Suite Languages 12.2.0.0.0 | Czech (optional) | varies | NO - unless Czech localization needed |
| Oracle E-Business Suite Languages 12.2.15 | (optional) | varies | NO |
| Oracle E-Business Suite Documentation 12.2.15 | N/A | 831.4 MB | OPTIONAL |
| Oracle Database 12.1.0.2.0 | Linux x86-64 | varies | NO - use 19c instead |
| Oracle E-Business Suite Mobile Application Archive 7.0 | Linux x86-64 | varies | NO |
| Oracle E-Business Suite Mobile Application Archive 9.1 | Linux x86-64 | varies | NO |
| Oracle E-Business Suite JET-based Mobile Applications 10 | Linux x86-64 | varies | NO |

**Total download (required only): approximately 75 GB**

> **NOTE:** The Vision Demo Database is NOT a separate download. It is included in "Oracle E-Business Suite 12.2.0 Current". You choose "Vision Demo Install" during Rapid Install.

### How to uncheck unnecessary items in edelivery:

In the Download Queue, uncheck the checkbox next to:
- Oracle E-Business Suite Languages 12.2.0.0.0
- Oracle E-Business Suite Languages 12.2.15
- Oracle Database 12.1.0.2.0
- Oracle E-Business Suite Mobile Application Archive 7.0
- Oracle E-Business Suite Mobile Application Archive 9.1
- Oracle E-Business Suite JET-based Mobile Applications 10

Keep checked:
- Oracle E-Business Suite 12.2.0 Current
- Oracle E-Business Suite 12.2.15
- Oracle E-Business Suite Documentation 12.2.15 (optional but useful)
- Oracle Database 19.3.0.0.0 - Long Term Release
- Oracle Web Tier 11.1.1.9.0
- Oracle WebLogic Server 10.3.6.0.0

After selecting platforms, click "Continue" to accept terms and download.

---

## Step 2: Create GCP Infrastructure (Automatable by AI Agent)

### 2.1 Create GCP Project and Enable APIs

```bash
# Create project (or use existing)
gcloud projects create keboola-oracle-ebs --name="Oracle EBS Dev"
gcloud config set project keboola-oracle-ebs

# Enable Compute Engine API
gcloud services enable compute.googleapis.com
```

### 2.2 Create Compute Engine VM

```bash
# Create VM instance
gcloud compute instances create oracle-ebs-vm \
  --zone=europe-west1-b \
  --machine-type=n2-standard-16 \
  --image-family=oracle-linux-8 \
  --image-project=oracle-linux-cloud \
  --boot-disk-size=500GB \
  --boot-disk-type=pd-ssd \
  --tags=oracle-ebs \
  --metadata=enable-oslogin=true

# Expected specs:
# - 16 vCPU, 64 GB RAM
# - 500 GB SSD boot disk
# - Oracle Linux 8 (x86-64)
# - Zone: europe-west1-b (Belgium, low latency from Prague)
```

**Budget alternative:** `n2-standard-8` (8 vCPU, 32 GB RAM, 400 GB SSD) - installation will be slower.

### 2.3 Configure Firewall Rules

```bash
# EBS web access
gcloud compute firewall-rules create allow-ebs-web \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:8000 \
  --source-ranges=0.0.0.0/0 --target-tags=oracle-ebs

# Oracle DB listener
gcloud compute firewall-rules create allow-oracle-db \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:1521 \
  --source-ranges=0.0.0.0/0 --target-tags=oracle-ebs

# VNC for Rapid Install GUI (TEMPORARY - remove after install)
gcloud compute firewall-rules create allow-vnc-temp \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:5901 \
  --source-ranges=0.0.0.0/0 --target-tags=oracle-ebs
```

> **Security:** After installation, restrict `source-ranges` to Keboola office IPs and remove VNC rule.

---

## Step 3: Upload Installation Media to VM (MANUAL)

```bash
# Option A: SCP from local machine
gcloud compute scp /path/to/ebs-downloads/*.zip oracle-ebs-vm:/u01/install/stage/ --zone=europe-west1-b

# Option B: Via GCS bucket (recommended for 75 GB)
# 1. Upload to bucket from local machine:
gsutil -m cp /path/to/ebs-downloads/*.zip gs://keboola-ebs-media/
# 2. Download to VM:
gcloud compute ssh oracle-ebs-vm --zone=europe-west1-b -- \
  "gsutil -m cp gs://keboola-ebs-media/*.zip /u01/install/stage/"
```

---

## Step 4: OS Configuration (Automatable by AI Agent)

### 4.1 Connect to VM

```bash
gcloud compute ssh oracle-ebs-vm --zone=europe-west1-b
```

### 4.2 System Update and Prerequisites

```bash
sudo dnf update -y

# Oracle Database prerequisites
sudo dnf install -y oracle-database-preinstall-19c

# Additional required packages
sudo dnf install -y \
  xorg-x11-server-Xvfb xorg-x11-apps xorg-x11-utils xorg-x11-xauth \
  tigervnc-server java-1.8.0-openjdk java-1.8.0-openjdk-devel \
  motif motif-devel redhat-lsb-core gcc gcc-c++ make binutils \
  glibc-devel libaio libaio-devel libstdc++-devel sysstat \
  unzip zip elfutils-libelf-devel fontconfig freetype ksh \
  libnsl libnsl2 compat-openssl10 xterm
```

### 4.3 Configure Swap Space (16 GB)

```bash
sudo dd if=/dev/zero of=/swapfile bs=1G count=16
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile swap swap defaults 0 0' | sudo tee -a /etc/fstab
free -h  # Verify: Swap ~16 GB
```

### 4.4 Configure Kernel Parameters

```bash
sudo tee -a /etc/sysctl.conf << 'EOF'
fs.file-max = 6815744
kernel.sem = 250 32000 100 128
kernel.shmmni = 4096
kernel.shmall = 1073741824
kernel.shmmax = 4398046511104
net.core.rmem_default = 262144
net.core.rmem_max = 4194304
net.core.wmem_default = 262144
net.core.wmem_max = 1048576
net.ipv4.ip_local_port_range = 9000 65500
fs.aio-max-nr = 1048576
EOF
sudo sysctl -p
```

### 4.5 Set Hostname

```bash
sudo hostnamectl set-hostname ebs.keboola.local
PRIVATE_IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/ip)
echo "${PRIVATE_IP} ebs.keboola.local ebs" | sudo tee -a /etc/hosts
hostname -f  # Verify: ebs.keboola.local
```

### 4.6 Create Oracle User and Directories

```bash
id oracle  # Should exist from preinstall package

sudo mkdir -p /u01/install/VISION
sudo mkdir -p /u01/install/stage
sudo mkdir -p /u01/oracle/VIS
sudo mkdir -p /u01/oracle/VIS/db/tech_st/19.0.0
sudo mkdir -p /u01/oracle/VIS/apps/tech_st/10.1.2
sudo mkdir -p /u01/oracle/VIS/apps/apps_st/appl
sudo chown -R oracle:oinstall /u01

df -h /u01  # Verify: at least 350 GB available
```

### 4.7 Set Up VNC Server

```bash
sudo su - oracle
vncpasswd  # Set password (remember this!)
vncserver :1 -geometry 1280x1024 -depth 24
vncserver -list  # Verify running
```

**Connect via SSH tunnel:**
```bash
gcloud compute ssh oracle-ebs-vm --zone=europe-west1-b -- -L 5901:localhost:5901
# Then connect VNC client to localhost:5901
```

---

## Step 5: Extract and Install EBS (PARTIALLY MANUAL - Rapid Install is GUI)

### 5.1 Extract Installation Media

```bash
sudo su - oracle
cd /u01/install/stage
unzip -o '*.zip' -d /u01/install/stage/
ls -la /u01/install/stage/startCD/Disk1/rapidwiz/  # Verify rapidwiz exists
```

### 5.2 Run Rapid Install (GUI via VNC - MANUAL)

**This step REQUIRES VNC connection. Rapid Install is an interactive GUI wizard.**

```bash
# In VNC session, as oracle user:
cd /u01/install/stage/startCD/Disk1/rapidwiz/
./rapidwiz
```

**Configuration parameters to enter in wizard:**

| Parameter | Value |
|-----------|-------|
| Install Type | **Vision Demo Install** |
| Database Type | Oracle Database 19c |
| Database SID | VIS |
| Database Port | 1521 |
| Apps Password | apps |
| System Password | manager |
| ORACLE_BASE | /u01/oracle/VIS |
| Database ORACLE_HOME | /u01/oracle/VIS/db/tech_st/19.0.0 |
| Apps ORACLE_HOME | /u01/oracle/VIS/apps/tech_st/10.1.2 |
| Instance Home | /u01/oracle/VIS/inst |
| Domain Name | keboola.local |
| Host Name | ebs.keboola.local |
| Web Entry Point | http://ebs.keboola.local:8000 |

**Expected duration: 4-8 hours**

### 5.3 Monitor Installation

```bash
# In separate SSH session:
tail -f /u01/install/VISION/rapidwiz/*.log
```

---

## Step 6: Post-Installation (Automatable by AI Agent)

### 6.1 Verify Services

```bash
sudo su - oracle
source /u01/oracle/VIS/apps/apps_st/appl/APPSVIS_ebs.env
$ADMIN_SCRIPTS_HOME/adstatus.sh
```

### 6.2 Configure External Access

```bash
EXTERNAL_IP=$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip)
echo "EBS Web UI: http://${EXTERNAL_IP}:8000/OA_HTML/AppsLogin"
```

### 6.3 Change Default Passwords

```bash
sqlplus apps/apps@VIS
# ALTER USER apps IDENTIFIED BY <new_secure_password>;
```

In EBS UI: Login as SYSADMIN/SYSADMIN, change password via System Administrator > Security > User > Define.

### 6.4 Clean Up

```bash
# Remove VNC firewall rule
gcloud compute firewall-rules delete allow-vnc-temp --quiet

# Stop VNC server
vncserver -kill :1

# Free disk space
rm -rf /u01/install/stage/*.zip
```

---

## Step 7: Validation Checklist

### Web Access
- [ ] Open `http://<EXTERNAL_IP>:8000/OA_HTML/AppsLogin`
- [ ] Login with SYSADMIN / SYSADMIN
- [ ] Navigate to GL, AP, AR modules
- [ ] Verify Vision demo data present

### Database Access
```sql
sqlplus apps/<password>@VIS

SELECT instance_name, status FROM v$instance;
-- Expected: VIS, OPEN

SELECT COUNT(*) FROM fnd_user;
-- Expected: > 0
```

### Remote DB Connection
```bash
sqlplus apps/<password>@<EXTERNAL_IP>:1521/VIS
```

### Key EBS Tables (for Extractor/Writer Development)
```sql
-- General Ledger
SELECT COUNT(*) FROM gl_je_headers;
SELECT COUNT(*) FROM gl_je_lines;
SELECT COUNT(*) FROM gl_balances;

-- Accounts Payable
SELECT COUNT(*) FROM ap_invoices_all;
SELECT COUNT(*) FROM ap_suppliers;

-- Accounts Receivable
SELECT COUNT(*) FROM ra_customer_trx_all;

-- Purchasing
SELECT COUNT(*) FROM po_headers_all;

-- Inventory
SELECT COUNT(*) FROM mtl_system_items_b;
```

---

## Cost Management

```bash
# Stop VM (saves compute, disk cost continues)
gcloud compute instances stop oracle-ebs-vm --zone=europe-west1-b

# Start VM
gcloud compute instances start oracle-ebs-vm --zone=europe-west1-b

# After start, restart EBS:
sudo su - oracle
source /u01/oracle/VIS/apps/apps_st/appl/APPSVIS_ebs.env
$ADMIN_SCRIPTS_HOME/adstrtal.sh apps/apps
```

| Resource | 24/7 | Work hours only |
|----------|------|-----------------|
| n2-standard-16 (64 GB) | ~$560/mo | ~$170/mo |
| 500 GB pd-ssd | ~$85/mo | ~$85/mo |
| **Total** | **~$645/mo** | **~$255/mo** |

---

## Access Details (After Installation)

| Resource | Value |
|----------|-------|
| EBS Web UI | `http://<EXTERNAL_IP>:8000/OA_HTML/AppsLogin` |
| Oracle DB | `<EXTERNAL_IP>:1521/VIS` |
| DB User | `apps / <password>` |
| EBS Admin | `SYSADMIN / SYSADMIN` (change immediately) |
| SSH | `gcloud compute ssh oracle-ebs-vm --zone=europe-west1-b` |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Rapid Install memory error | Verify 32+ GB RAM, 16 GB swap: `free -h` |
| GUI won't start | Check VNC: `vncserver -list`, check `$DISPLAY` |
| Web UI not accessible | Check services: `$ADMIN_SCRIPTS_HOME/adstatus.sh`, firewall: `gcloud compute firewall-rules list` |
| TNS:no listener remotely | Edit `$ORACLE_HOME/network/admin/listener.ora` to bind 0.0.0.0, restart: `lsnrctl stop && lsnrctl start` |
| Disk space low | Remove staging: `rm -rf /u01/install/stage/*.zip` |

---

## References

- [Oracle EBS on Google Cloud (official)](https://docs.cloud.google.com/architecture/oracle-ebs-on-compute-engine-vm)
- [Oracle EBS Rapid Install Guide](https://docs.oracle.com/cd/E26401_01/doc.122/e22950/T422699i4773.htm)
- [Oracle Software Delivery Cloud](https://edelivery.oracle.com)
- [OPN Partner Hub](https://partners.oracle.com)
- MOS Doc ID 1330701.1 - EBS Installation Notes for Linux x86-64
