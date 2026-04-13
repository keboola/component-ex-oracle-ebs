# Oracle E-Business Suite 12.2.12 on GCP - Deployment Guide (Proven Path)

## Overview

This guide documents the **proven, working procedure** for deploying Oracle E-Business Suite 12.2.12 Vision Demo on Google Cloud Platform. It uses the Oracle VM Virtual Appliance approach, which bypasses the complex Rapid Install process.

**Result:** Fully functional EBS 12.2.12 with DB 19c, Vision Demo data (millions of records), running on GCP Compute Engine.

**Time required:** ~3-4 hours (mostly download/upload wait time)

---

## Why VM Appliance (Not Rapid Install)

We originally attempted Rapid Install from scratch on Oracle Linux 8. This failed due to:

1. **OUI 12c incompatibility with OL8** - The Oracle Universal Installer bundled with DB 12.1.0.2 has bugs on Oracle Linux 8:
   - `-ignoreSharedInventory` flag added internally but not recognized by its own version
   - `getFont()` NoSuchMethodError due to conflicting OCM JAR versions (`jlib/jlib/` path issue)
   - `OUI-10082: The staging area needs Oracle Universal Installer version 11.2.0.2.0 or later`
2. **Oracle Linux 7 not available on GCP** - GCP only offers OL8+, CentOS 7 is EOL
3. **MOS patches required but inaccessible** - Fixes (patches 32947483, 36332179, 29963728, 6078836) are on My Oracle Support, which requires a CSI (Customer Support Identifier) not included with OPN Level 1

The VM Appliance from edelivery.oracle.com contains a pre-built, fully configured EBS instance that just works.

---

## Prerequisites

### Accounts Required
- Oracle Partner Network account (for edelivery.oracle.com access)
- GCP project with Compute Engine API enabled
- GCP account with `roles/compute.admin` and `roles/storage.admin`

### Local Tools
- `gcloud` CLI configured and authenticated
- SSH key pair (`~/.ssh/google_compute_engine`)

---

## Step 1: Download VM Appliance from edelivery.oracle.com

### 1.1 Create a temporary GCP VM for downloads

```bash
gcloud compute instances create ebs-download-vm \
  --zone=europe-west1-b \
  --machine-type=n2-standard-8 \
  --image-family=oracle-linux-8 \
  --image-project=oracle-linux-cloud \
  --boot-disk-size=500GB \
  --boot-disk-type=pd-ssd \
  --tags=oracle-ebs \
  --metadata=enable-oslogin=true \
  --scopes=storage-full,compute-rw
```

### 1.2 Set up VNC + noVNC on the download VM

Downloads from edelivery.oracle.com require browser authentication (IP-bound tokens). Set up a browser on the VM:

```bash
gcloud compute ssh ebs-download-vm --zone=europe-west1-b

# Install packages
sudo dnf install -y tigervnc-server firefox gnome-screenshot python3-pillow

# Create oracle user (for VNC)
sudo useradd -m oracle
sudo su - oracle

# Start VNC
vncpasswd  # set password e.g. oracle123
vncserver :1 -geometry 1280x1024 -depth 24

# Install noVNC for browser-based VNC access
exit  # back to root
sudo dnf install -y python3 git
cd /opt
sudo git clone https://github.com/novnc/noVNC.git
sudo git clone https://github.com/novnc/websockify.git /opt/noVNC/utils/websockify
sudo /opt/noVNC/utils/novnc_proxy --vnc localhost:5901 --listen 6080 &
```

Create firewall rule for noVNC:
```bash
gcloud compute firewall-rules create allow-novnc-temp \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:6080 \
  --source-ranges=YOUR_IP/32 --target-tags=oracle-ebs
```

Access via: `http://<VM_EXTERNAL_IP>:6080/vnc.html` (password: oracle123)

### 1.3 Download the appliance

1. Open Firefox on VM via noVNC
2. Go to https://edelivery.oracle.com, login with OPN credentials
3. Search for **"Oracle VM Virtual Appliance for Oracle E-Business Suite"**
4. Select **REL** (Release, not DLP) for version **12.2.12** (or latest available)
5. Select platform **Linux x86-64**
6. Download all files via **WGET Options** → download wget.sh
7. Download the wget.sh via Firefox (saves to VM)

The wget.sh contains ~20 files totaling ~68 GB. Some files download via wget with Bearer token, others require browser-based download. For files that fail with wget (401 errors), open their URLs directly in Firefox.

**Important:** edelivery download tokens expire quickly. Download wget.sh, get a fresh access token, and start downloads immediately.

### 1.4 Assemble the OVA

```bash
# As oracle user
cd /path/to/downloads

# Extract assemble script from the README zip (V1034613-01.zip)
unzip V1034613-01.zip -d /tmp/readme
cd /tmp/readme/V1034613-01
unzip assemble_12212.zip
cp assemble/VISION_INSTALL_MEDIA/* /path/to/downloads/

# Run assembler
cd /path/to/downloads
chmod +x assemble.sh
bash assemble.sh
# Follow prompts, takes ~15 minutes
# Result: Oracle-E-Business-Suite-12.2.12_VISION_INSTALL.ova (~72 GB)
```

---

## Step 2: Convert OVA to GCP Image

### 2.1 Extract VMDK from OVA

```bash
cd /path/to/downloads
tar xf Oracle-E-Business-Suite-12.2.12_VISION_INSTALL.ova \
  Oracle-E-Business-Suite-12.2.12_VISION_INSTALL-disk001.vmdk
```

### 2.2 Upload VMDK to GCS

```bash
# Create GCS bucket
gcloud storage buckets create gs://YOUR-BUCKET --location=europe-west1

# Upload from VM (fast internal network ~130 MB/s)
# Option A: If gsutil/gcloud is available on VM:
gsutil cp Oracle-E-Business-Suite-12.2.12_VISION_INSTALL-disk001.vmdk gs://YOUR-BUCKET/

# Option B: Python upload script (if gsutil not available):
# Use the gcs_upload.py script that does resumable upload via VM service account token
python3 gcs_upload.py  # ~10 minutes for 72 GB
```

### 2.3 Import as GCE Image

```bash
# Enable Cloud Build API (required for image import)
gcloud services enable cloudbuild.googleapis.com --project=YOUR_PROJECT

# Import VMDK as GCE image
gcloud compute images import ebs-12212-vision \
  --project=YOUR_PROJECT \
  --source-file=gs://YOUR-BUCKET/Oracle-E-Business-Suite-12.2.12_VISION_INSTALL-disk001.vmdk \
  --os=rhel-7 \
  --no-guest-environment \
  --quiet \
  --log-location=gs://YOUR-BUCKET/logs

# Takes 15-30 minutes. Image will be named "ebs-12212-vision"
```

---

## Step 3: Create EBS VM from Image

```bash
gcloud compute instances create oracle-ebs-appliance \
  --zone=europe-west1-b \
  --machine-type=n2-standard-8 \
  --image=ebs-12212-vision \
  --boot-disk-size=400GB \
  --boot-disk-type=pd-ssd \
  --tags=oracle-ebs \
  --metadata=enable-oslogin=FALSE
```

### 3.1 Inject SSH Keys (Required - Appliance doesn't have GCP guest agent)

The appliance image doesn't support GCP OS Login or metadata SSH keys natively. You must inject keys via a rescue VM:

```bash
# Stop the EBS VM
gcloud compute instances stop oracle-ebs-appliance --zone=europe-west1-b

# Start the download VM as rescue
gcloud compute instances start ebs-download-vm --zone=europe-west1-b

# Detach EBS disk and attach to rescue VM
gcloud compute instances detach-disk oracle-ebs-appliance --disk=oracle-ebs-appliance --zone=europe-west1-b
gcloud compute instances attach-disk ebs-download-vm --disk=oracle-ebs-appliance --zone=europe-west1-b --device-name=ebs-disk

# SSH to rescue VM
gcloud compute ssh ebs-download-vm --zone=europe-west1-b

# On rescue VM: activate LVM, mount, inject keys
sudo vgchange -ay
sudo mount /dev/ol/root /mnt/ebs
sudo mount /dev/ol/home /mnt/ebs/home

# Inject SSH keys
SSH_KEY="ssh-rsa AAAA... your-key"
sudo mkdir -p /mnt/ebs/root/.ssh /mnt/ebs/home/oracle/.ssh
echo "$SSH_KEY" | sudo tee /mnt/ebs/root/.ssh/authorized_keys /mnt/ebs/home/oracle/.ssh/authorized_keys
sudo chmod 700 /mnt/ebs/root/.ssh /mnt/ebs/home/oracle/.ssh
sudo chmod 600 /mnt/ebs/root/.ssh/authorized_keys /mnt/ebs/home/oracle/.ssh/authorized_keys

# Fix ownership for oracle
ORACLE_UID=$(grep oracle /mnt/ebs/etc/passwd | cut -d: -f3)
ORACLE_GID=$(grep oracle /mnt/ebs/etc/passwd | cut -d: -f4)
sudo chown -R $ORACLE_UID:$ORACLE_GID /mnt/ebs/home/oracle/.ssh

# Fix SELinux context
sudo restorecon -R /mnt/ebs/root/.ssh /mnt/ebs/home/oracle/.ssh 2>/dev/null

# Enable SSH pubkey auth
sudo sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' /mnt/ebs/etc/ssh/sshd_config
sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin yes/' /mnt/ebs/etc/ssh/sshd_config

# Set passwords (root and oracle)
HASH=$(python3 -c "import crypt; print(crypt.crypt('manager1', crypt.mksalt(crypt.METHOD_SHA512)))")
sudo sed -i "s|^root:[^:]*:|root:$HASH:|" /mnt/ebs/etc/shadow
sudo sed -i "s|^oracle:[^:]*:|oracle:$HASH:|" /mnt/ebs/etc/shadow

# Disable forced password change on first login
sudo sed -i 's/^root:\([^:]*\):0:/root:\1:19823:/' /mnt/ebs/etc/shadow
sudo sed -i 's/^oracle:\([^:]*\):0:/oracle:\1:19823:/' /mnt/ebs/etc/shadow

# Create .passchanged marker (skips appliance password dialog)
sudo touch /mnt/ebs/root/.passchanged

# Set hostname
echo "10.132.0.3 apps.example.com apps" | sudo tee -a /mnt/ebs/etc/hosts

# Unmount and deactivate LVM
sudo umount /mnt/ebs/home /mnt/ebs
sudo vgchange -an ol

# Disconnect from rescue VM
exit

# Swap disks back
gcloud compute instances stop ebs-download-vm --zone=europe-west1-b
gcloud compute instances detach-disk ebs-download-vm --disk=oracle-ebs-appliance --zone=europe-west1-b
gcloud compute instances attach-disk oracle-ebs-appliance --disk=oracle-ebs-appliance --zone=europe-west1-b --boot
gcloud compute instances start oracle-ebs-appliance --zone=europe-west1-b
```

### 3.2 Configure Firewall

```bash
YOUR_IP=$(curl -s ifconfig.me)

gcloud compute firewall-rules create allow-ebs-web \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:8000 \
  --source-ranges=$YOUR_IP/32 --target-tags=oracle-ebs

gcloud compute firewall-rules create allow-oracle-db \
  --direction=INGRESS --priority=1000 --network=default \
  --action=ALLOW --rules=tcp:1521 \
  --source-ranges=$YOUR_IP/32 --target-tags=oracle-ebs
```

### 3.3 Add /etc/hosts entry on your local machine

```bash
EBS_IP=$(gcloud compute instances describe oracle-ebs-appliance --zone=europe-west1-b --format="value(networkInterfaces[0].accessConfigs[0].natIP)")
sudo sh -c "echo '$EBS_IP apps.example.com' >> /etc/hosts"
```

**Note:** Update this entry every time the VM gets a new external IP (on restart).

---

## Step 4: Start EBS Services

```bash
ssh -i ~/.ssh/google_compute_engine root@<EBS_IP>

# Start database
su - oracle -c '/u01/install/APPS/scripts/startdb.sh'

# Start application tier
su - oracle -c '/u01/install/APPS/scripts/startapps.sh'
```

### 4.1 Set SYSADMIN Password

The appliance has SYSADMIN with an expired/unknown password. Reset it:

```bash
su - oracle
source /u01/install/APPS/EBSapps.env run
export ORACLE_SID=EBSDB

sqlplus -s apps/apps <<EOF
EXEC fnd_user_pkg.UpdateUser(x_user_name => 'SYSADMIN', x_owner => 'CUST', x_unencrypted_password => 'manager1');
COMMIT;
EOF
```

### 4.2 Verify

- **Web UI:** http://apps.example.com:8000/OA_HTML/AppsLocalLogin.jsp
  - Login: SYSADMIN / manager1
- **SSH:** `ssh -i ~/.ssh/google_compute_engine root@<EBS_IP>`
- **DB:** `sqlplus apps/apps@<EBS_IP>:1521/ebs_EBSDB`

---

## Step 5: Configure API Access (ISG - Integrated SOA Gateway)

> **STATUS: COMPLETE** - All 6 REST services deployed, granted, and tested (2026-04-12)

### 5.1 ISG Current State

The appliance has ISG framework running with:
- 4,391 interfaces registered in the repository
- 862 PL/SQL and SOAP services available for deployment
- REST framework responding at `/webservices/rest/` (returns JSON errors for invalid aliases)
- SOAP framework at `/webservices/SOAProvider/`

### 5.2 ISG REST Setup (One-Time)

```bash
su - oracle
source /u01/install/APPS/EBSapps.env run
export ORACLE_SID=EBSDB

# Run ISG REST configuration (sets up ISG datasource and ASADMIN credential)
# Prompts for: APPS password, WLS admin user, WLS admin password
echo -e "apps\nweblogic\nmanager1" | perl $FND_TOP/patch/115/bin/ISGRestSetup.pl

# Verify: should return "ACTIVE"
curl -s -u SYSADMIN:manager1 http://localhost:8000/webservices/rest/provider/isActive/
```

### 5.3 Deploy REST Services

```bash
su - oracle
source /u01/install/APPS/EBSapps.env run
export ORACLE_SID=EBSDB

# Deploy each API as REST service using ant script
for ENTRY in "FND_USER_PKG:fnduser" "HZ_PARTY_V2PUB:hzparty" "AR_INVOICE_API_PUB:arinvoice" \
             "GL_JOURNAL_IMPORT_PKG:gljournal" "HZ_PARTY_SITE_V2PUB:hzpartysite" \
             "HZ_CUST_ACCOUNT_V2PUB:hzcustaccount"; do
  API="${ENTRY%%:*}"
  ALIAS="${ENTRY##*:}"
  echo "Deploying $API as /$ALIAS..."
  ant -f $JAVA_TOP/oracle/apps/fnd/isg/ant/isgDesigner.xml \
    -Dactions="deploy" -DserviceType=REST \
    -DirepNames="$API" -Dalias="$ALIAS" -DauthType=BOTH -Dverbose=OFF
done

# Verify: all should return HTTP 200
for svc in fnduser hzparty arinvoice gljournal hzpartysite hzcustaccount; do
  echo "$svc: $(curl -s -o /dev/null -w '%{http_code}' -u SYSADMIN:manager1 http://localhost:8000/webservices/rest/$svc?WADL)"
done
```

### 5.4 Grant REST Access (Required for Each Service)

ISG REST requires per-operation grants in FND_GRANTS. Without them, POST calls return HTTP 403 (`ISG_SERVICE_AUTH_FAILURE`). WADL/GET calls work without grants.

**Method: SQL (Recommended - faster and more reliable than UI)**

The grant mechanism uses:
- Object: `FND_REP_FUNCTION_FLAVORS_OBJ` (object_id 3306)
- Instance Set: `FND_REP_FUNC_FLAVORS_INST` (instance_set_id 2949)
- Menu: `FND_FUNCTION_<function_id>` (auto-created single-function menus)
- PARAMETER1 = function_id, PARAMETER2 = overload_seq
- Grantee: GLOBAL/GLOBAL (All Users)

```sql
-- Connect to DB: sqlplus apps/apps@(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=localhost)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=ebs_EBSDB)))

-- Step 1: Find function_id and overload_seq for your API operations
SELECT ff.function_id, ff.overload_seq, f.function_name
FROM fnd_irep_function_flavors ff
JOIN fnd_form_functions f ON ff.function_id = f.function_id
WHERE f.function_name LIKE 'PLSQL:HZ_PARTY_V2PUB%'  -- change to your API
ORDER BY f.function_name, ff.overload_seq;

-- Step 2: Create grants using fnd_grants_pkg.grant_function
DECLARE
  l_grant_guid RAW(16);
  l_success VARCHAR2(1);
  l_error_code NUMBER;
BEGIN
  fnd_grants_pkg.grant_function(
    p_api_version       => 1.0,
    p_menu_name         => 'FND_FUNCTION_<function_id>',  -- e.g., FND_FUNCTION_1065994
    p_object_name       => 'FND_REP_FUNCTION_FLAVORS_OBJ',
    p_instance_type     => 'SET',
    p_instance_set_id   => 2949,
    p_grantee_type      => 'GLOBAL',
    p_grantee_key       => 'GLOBAL',
    p_start_date        => SYSDATE,
    p_end_date          => NULL,
    p_program_name      => 'ISG_REST',
    p_program_tag       => 'description',
    x_grant_guid        => l_grant_guid,
    x_success           => l_success,
    x_errorcode         => l_error_code,
    p_parameter1        => '<function_id>',    -- e.g., '1065994'
    p_parameter2        => '<overload_seq>'    -- e.g., '1'
  );
  COMMIT;
END;
/
```

The SQL script `/tmp/create_isg_grants_v3.sql` on the server contains grants for all 38 operations across 6 services.

**Method: UI (Alternative)**

1. Login as SYSADMIN, navigate to Integration Repository
2. Search for the API Internal Name (e.g., `HZ_PARTY_V2PUB`)
3. Click on the interface link
4. Go to **Grants** tab, select all operations, click **Create Grant**
5. Set Grantee Type = **All Users**, click Create

**Note:** The Grants tab grants work but may link to wrong menu_id values. The SQL method is more reliable.

**Responsibility Assignments (Required for RESTHeader context)**

Some APIs (AR, GL) require a RESTHeader with Responsibility/RespApplication. SYSADMIN needs:

```sql
-- Assign responsibilities to SYSADMIN for API context
-- Already assigned: RECEIVABLES_MANAGER (AR), PAYABLES_MANAGER (SQLAP),
-- PURCHASING_SUPER_USER (PO), GENERAL_LEDGER_SUPER_USER (SQLGL)
-- If GL assignment is expired from Vision demo data, reactivate:
BEGIN
  fnd_user_resp_groups_api.update_assignment(
    user_id => (SELECT user_id FROM fnd_user WHERE user_name = 'SYSADMIN'),
    responsibility_id => 20434,  -- GENERAL_LEDGER_SUPER_USER
    responsibility_application_id => 101,  -- SQLGL
    security_group_id => 0,
    start_date => TRUNC(SYSDATE),
    end_date => NULL,
    description => 'ISG REST API access'
  );
  COMMIT;
END;
/
```

### 5.5 REST Endpoint URLs

```
Base: http://apps.example.com:8000/webservices/rest/

WADL (service discovery):
  http://apps.example.com:8000/webservices/rest/{alias}?WADL

Operations:
  POST http://apps.example.com:8000/webservices/rest/{alias}/{operation}/

Authentication: HTTP Basic (EBS username/password)
Content-Type: application/json
```

| Alias | API | Operations (all granted, all tested) | Status |
|-------|-----|--------------------------------------|--------|
| fnduser | FND_USER_PKG | testusername, isuseractive, isuseractive__1, validate_user_name, derive_person_party_id, load_row, change_user_name, set_old_person_party_id, set_old_user_guid, remove_pii_user, ldap_wrapper_create_user, ldap_wrapper_update_user, ldap_wrapper_change_user_name, ldap_wrp_update_user_loader, form_ldap_wrapper_update_user | All 200 |
| hzparty | HZ_PARTY_V2PUB | create_person, create_organization, create_group, update_person, update_organization, update_group | All 200 |
| arinvoice | AR_INVOICE_API_PUB | create_invoice, create_single_invoice | 500 (PL/SQL runtime error, grants OK) |
| gljournal | GL_JOURNAL_IMPORT_PKG | get_error_msg, get_last_sql, populate_interface_control, create_table, drop_table | 200 (needs RESTHeader with GL resp) |
| hzpartysite | HZ_PARTY_SITE_V2PUB | create_party_site, update_party_site, create_party_site_use, update_party_site_use | All 200 |
| hzcustaccount | HZ_CUST_ACCOUNT_V2PUB | create_cust_account, create_cust_account__1, update_cust_account, create_cust_acct_relate, create_cust_acct_relate__1, update_cust_acct_relate | All 200 |

### 5.6 REST Call Examples (Tested & Working)

**fnduser - Check if user is active:**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/fnduser/isuseractive/" \
  -d '{"InputParameters": {"USERNAME": "SYSADMIN"}}'
# Returns: {"OutputParameters": {"FND_USER_PKG-24ISUSERACTIVE": "0"}}  (0=active)
```

**hzparty - Create a person:**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzparty/create_person/" \
  -d '{"InputParameters": {"P_INIT_MSG_LIST": "T", "P_PERSON_REC": {"PERSON_FIRST_NAME": "John", "PERSON_LAST_NAME": "Doe", "CREATED_BY_MODULE": "TCA_V2_API"}}}'
# Returns: X_PARTY_ID, X_PARTY_NUMBER, X_PROFILE_ID, X_RETURN_STATUS="S"
```

**hzparty - Create an organization:**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzparty/create_organization/" \
  -d '{"InputParameters": {"P_INIT_MSG_LIST": "T", "P_ORGANIZATION_REC": {"ORGANIZATION_NAME": "Acme Corp", "CREATED_BY_MODULE": "TCA_V2_API"}}}'
# Returns: X_PARTY_ID, X_PARTY_NUMBER, X_PROFILE_ID, X_RETURN_STATUS="S"
```

**hzcustaccount - Create customer account with person:**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzcustaccount/create_cust_account/" \
  -d '{"InputParameters": {"P_INIT_MSG_LIST": "T", "P_CUST_ACCOUNT_REC": {"ACCOUNT_NAME": "Acme Account", "CREATED_BY_MODULE": "TCA_V2_API"}, "P_PERSON_REC": {"PERSON_FIRST_NAME": "Jane", "PERSON_LAST_NAME": "Smith", "CREATED_BY_MODULE": "TCA_V2_API"}}}'
# Returns: X_CUST_ACCOUNT_ID, X_ACCOUNT_NUMBER, X_PARTY_ID, X_RETURN_STATUS="S"
```

**hzpartysite - Create party site:**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/hzpartysite/create_party_site/" \
  -d '{"InputParameters": {"P_INIT_MSG_LIST": "T", "P_PARTY_SITE_REC": {"PARTY_ID": 476201, "LOCATION_ID": 919, "PARTY_SITE_NAME": "HQ", "CREATED_BY_MODULE": "TCA_V2_API"}}}'
# Returns: X_PARTY_SITE_ID, X_PARTY_SITE_NUMBER, X_RETURN_STATUS="S"
```

**gljournal - With RESTHeader (required for GL context):**
```bash
curl -X POST -u SYSADMIN:manager1 \
  -H "Content-Type: application/json" -H "Accept: application/json" \
  "http://apps.example.com:8000/webservices/rest/gljournal/populate_interface_control/" \
  -d '{"RESTHeader": {"Responsibility": "GENERAL_LEDGER_SUPER_USER", "RespApplication": "SQLGL", "SecurityGroup": "STANDARD", "NLSLanguage": "AMERICAN", "Org_Id": "204"}, "InputParameters": {"USER_JE_SOURCE_NAME": "Manual", "GROUP_ID": 1, "SET_OF_BOOKS_ID": 1, "INTERFACE_RUN_ID": 99999, "TABLE_NAME": "GL_INTERFACE", "PROCESSED_DATA_ACTION": "D"}}'
# Returns: GROUP_ID, INTERFACE_RUN_ID
```

**Note:** APIs requiring org context (AR, GL, AP) need the RESTHeader with appropriate Responsibility/RespApplication. TCA APIs (hzparty, hzpartysite, hzcustaccount) work without RESTHeader.
```

### 5.7 Key APIs Available

| API | Type | Module | Purpose |
|-----|------|--------|---------|
| AP_INVOICES_PKG | PL/SQL | Payables | Invoice CRUD |
| GL_JOURNAL_IMPORT_PKG | PL/SQL | GL | Journal import |
| HZ_PARTY_V2PUB | PL/SQL | TCA | Party/customer management |
| HZ_CUST_ACCOUNT_V2PUB | PL/SQL | TCA | Customer accounts |
| FND_USER_PKG | PL/SQL | Foundation | User management |
| AR_INVOICE_API_PUB | PL/SQL | Receivables | AR invoice creation |
| PO_HEADERS_INTERFACE | Interface Table | Purchasing | PO import |
| AP_INVOICES_INTERFACE | Interface Table | Payables | Invoice import |
| GL_INTERFACE | Interface Table | GL | Journal import |

### 5.8 JDBC Access (Works Immediately)

No ISG setup needed for JDBC. Connect directly:

```
Host: apps.example.com (or VM external IP)
Port: 1521
Service: ebs_EBSDB
Username: apps
Password: apps
```

---

## Vision Demo Data Summary

| Table | Records | Module |
|-------|---------|--------|
| gl_je_headers | 177,917 | General Ledger |
| gl_je_lines | 3,155,216 | General Ledger |
| gl_balances | 8,232,309 | General Ledger |
| ap_invoices_all | 145,489 | Accounts Payable |
| ap_suppliers | 426 | Accounts Payable |
| ra_customer_trx_all | 69,665 | Accounts Receivable |
| po_headers_all | 27,285 | Purchasing |
| po_lines_all | 118,894 | Purchasing |
| mtl_system_items_b | 27,712 | Inventory |
| per_all_people_f | 33,854 | HR |
| fnd_user | 3,369 | Foundation |

---

## Cost Management

```bash
# Stop VM (saves compute cost, disk cost continues ~$85/mo)
gcloud compute instances stop oracle-ebs-appliance --zone=europe-west1-b

# Start VM
gcloud compute instances start oracle-ebs-appliance --zone=europe-west1-b
# Then: start DB + Apps (see Step 4)
# Then: update /etc/hosts with new IP
```

| Resource | 24/7 | Work hours only (~10h/day) |
|----------|------|---------------------------|
| n2-standard-8 (32 GB) | ~$280/mo | ~$85/mo |
| 400 GB pd-ssd | ~$68/mo | ~$68/mo |
| **Total** | **~$348/mo** | **~$153/mo** |

---

## Key Access Details

| Resource | Value |
|----------|-------|
| VM Name | oracle-ebs-appliance |
| Zone | europe-west1-b |
| Project | components-factory-dev |
| OS | Oracle Linux 7.9 |
| EBS Version | 12.2.12 |
| DB Version | Oracle 19c (CDB: EBSCDB, PDB service: ebs_EBSDB) |
| EBS Web UI | http://apps.example.com:8000 |
| EBS Login | SYSADMIN / manager1 |
| DB Connect | apps/apps @ <IP>:1521/ebs_EBSDB |
| SSH | ssh -i ~/.ssh/google_compute_engine root@<IP> |
| root password | manager1 |
| oracle password | manager1 |
| EBS Home | /u01/install/APPS/ |
| Scripts | /u01/install/APPS/scripts/ |
| Start DB | /u01/install/APPS/scripts/startdb.sh |
| Start Apps | /u01/install/APPS/scripts/startapps.sh |
| Stop DB | /u01/install/APPS/scripts/stopdb.sh |
| Stop Apps | /u01/install/APPS/scripts/stopapps.sh |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| SSH permission denied | Inject SSH keys via rescue VM (see Step 3.1) |
| Web UI shows "apps.example.com can't be reached" | Add `/etc/hosts` entry: `<IP> apps.example.com` |
| 503 after VM restart | Wait 5-10 min for WLS managed servers to start, or run `startapps.sh` |
| Password expired | Reset via sqlplus: `EXEC fnd_user_pkg.UpdateUser(...)` |
| External IP changed | Update `/etc/hosts` locally |
| DB not starting | Check: `ps -fu oracle \| grep pmon`. If missing, run `startdb.sh` |
| ISG REST returns 405 | Services not yet deployed - see Step 5 |

---

## Cleanup (When Done)

```bash
# Delete VMs
gcloud compute instances delete oracle-ebs-appliance --zone=europe-west1-b --quiet
gcloud compute instances delete ebs-download-vm --zone=europe-west1-b --quiet

# Delete image
gcloud compute images delete ebs-12212-vision --quiet

# Delete GCS bucket
gcloud storage rm -r gs://YOUR-BUCKET

# Delete firewall rules
gcloud compute firewall-rules delete allow-ebs-web allow-oracle-db allow-novnc-temp --quiet

# Delete snapshot
gcloud compute snapshots delete ebs-stage-snapshot --quiet
```
