# Bước 2 - CI/CD với Amazon S3 và EC2

Mục tiêu: mỗi lần push code hoặc con trỏ dữ liệu DVC lên `main`, GitHub Actions chạy unit test, kéo dữ liệu từ S3, huấn luyện, kiểm tra `f1_score >= 0.65`, tải model lên S3 và restart API trên EC2.

Lab này dùng AWS. Máy local cần AWS CLI v2, DVC với extra S3 và profile AWS đã đăng nhập bằng IAM Identity Center/SSO. Không lưu access key trong repo. Tài nguyên S3/EC2/IAM và truyền dữ liệu có thể phát sinh chi phí; kiểm tra AWS Billing, giới hạn lab và xóa tài nguyên cloud sau khi kết thúc.

## 2.1 Tạo bucket S3

Chọn một AWS Region và tên bucket duy nhất. Trên máy local:

```bash
export AWS_REGION=ap-southeast-1
export BUCKET=<TEN_BUCKET_DUY_NHAT>
aws configure sso
aws sso login
aws sts get-caller-identity
```

Tạo bucket. Với `us-east-1`, bỏ `--create-bucket-configuration`; các region khác dùng lệnh dưới:

```bash
aws s3api create-bucket \
  --bucket "$BUCKET" \
  --region "$AWS_REGION" \
  --create-bucket-configuration "LocationConstraint=$AWS_REGION"

aws s3api put-public-access-block \
  --bucket "$BUCKET" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

aws s3api put-bucket-encryption \
  --bucket "$BUCKET" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
```

Giữ bucket private; workflow và EC2 truy cập bằng IAM. DVC objects sẽ nằm dưới prefix `dvc/`, model ở `artifacts/current/model.joblib`.

## 2.2 DVC remote và phiên bản hóa dữ liệu

Từ thư mục gốc repo, sau khi Bước 1 đã tạo 3 CSV:

```bash
dvc init
dvc remote add -d labstore "s3://$BUCKET/dvc"
dvc add data/train_batch1.csv
dvc add data/holdout.csv
dvc add data/train_batch2.csv
git add .dvc .dvcignore .gitignore data/*.dvc
git commit -m "data: track datasets with DVC"
dvc push
```

DVC dùng AWS credential chain, nên profile SSO đang đăng nhập được dùng trên máy local. Đừng thêm access key hoặc session token vào `.dvc/config`. Xác nhận các objects xuất hiện trong S3 Console dưới `dvc/`. Chỉ commit file `.dvc`, không commit CSV.

## 2.3 Tạo IAM role cho GitHub Actions (OIDC)

Workflow dùng `aws-actions/configure-aws-credentials` và GitHub OIDC để nhận credentials ngắn hạn. Trong IAM:

1. Tạo OIDC identity provider `https://token.actions.githubusercontent.com` với audience `sts.amazonaws.com` nếu account chưa có.
2. Tạo role tin cậy provider đó. Giới hạn `token.actions.githubusercontent.com:aud` là `sts.amazonaws.com` và `token.actions.githubusercontent.com:sub` đúng repo/branch:
   `repo:yohan-vinai/K4-L3-DAY21-VoPhuHan-2A202602628-CI-CD-for-AI-Systems:ref:refs/heads/main`.
3. Gắn policy chỉ cho phép đọc object dưới `dvc/` và ghi model tại `artifacts/current/model.joblib` trong bucket của lab. DVC cần đọc object và liệt kê prefix; không cấp quyền bucket-wide hoặc quyền xóa nếu không cần.
4. Ghi lại ARN role để tạo GitHub secret `AWS_ROLE_ARN` ở mục 2.8.

Để sinh policy từ các file Python dùng boto3, chạy IAM Policy Autopilot sau khi cài `uv`:

```bash
uvx iam-policy-autopilot@latest generate-policies \
  "$PWD/src/serve.py" \
  "$PWD/scripts/upload_release.py" \
  "$PWD/scripts/release_ssm.py" \
  --account "$(aws sts get-caller-identity --query Account --output text)" \
  --region "$AWS_REGION" \
  --service-hints s3 ssm \
  --pretty
```

Dùng kết quả làm đầu vào cho GitHub role, rồi giới hạn S3 resources vào đúng bucket/prefix và SSM vào đúng instance. Kiểm tra các cảnh báo wildcard của Autopilot trước khi gắn policy; không cấp `iam:PassRole` nếu role này không cần truyền IAM role. DVC dùng AWS API qua CLI nên role còn cần quyền liệt kê bucket (giới hạn prefix `dvc/`) và đọc object dưới `dvc/`. EC2 role cần `s3:GetObject` cho `artifacts/current/*` và managed policy `AmazonSSMManagedInstanceCore`. Không tạo IAM access key cho Actions hoặc EC2.

## 2.4 Tạo EC2 và quyền đọc model

Trong EC2 Console, chọn Ubuntu Server LTS x86_64, instance nhỏ phù hợp lab (ví dụ `t3.small`), storage EBS đã bật mã hóa và bật IMDSv2. Gắn EC2 instance profile role có `AmazonSSMManagedInstanceCore` và quyền đọc `artifacts/current/*` trong bucket này. Đợi SSM Managed Instance hiển thị instance là **Online**.

Security group:

- API TCP 8080 chỉ từ IP hiện tại của a để kiểm tra bằng curl. Không mở API demo ra toàn Internet.
- Outbound mặc định cho phép HTTPS để EC2 lấy model từ S3.

Không mở cổng SSH inbound cho pipeline. Dùng AWS Systems Manager Session Manager cho lần cấu hình đầu và GitHub Actions release; lưu `Instance ID` và bucket/region.

## 2.5 Cài FastAPI service trên EC2

Mở **EC2 → Instances → Connect → Session Manager**. Lần đầu cấu hình instance:

```bash
sudo apt update
sudo apt install -y python3-venv awscli curl
mkdir -p ~/income-api/src ~/models
python3 -m venv ~/income-api/.venv
~/income-api/.venv/bin/pip install fastapi uvicorn scikit-learn joblib boto3
```

Tạo `/etc/systemd/system/income-api.service`:

```ini
[Unit]
Description=Income Model Inference API
After=network-online.target
Wants=network-online.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/income-api
Environment="ARTIFACT_BUCKET=<TEN_BUCKET>"
Environment="AWS_DEFAULT_REGION=<AWS_REGION>"
ExecStart=/home/ubuntu/income-api/.venv/bin/uvicorn src.serve:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Kích hoạt service. Source và model sẽ được tải từ S3 khi Release job đầu tiên chạy:

```bash
sudo systemctl daemon-reload
sudo systemctl enable income-api
```

`src/serve.py` lấy credentials tự động từ EC2 instance profile; không chép AWS keys lên máy chủ. Unit file phải được enable trước lần chạy Actions đầu tiên; Release job sẽ start service lần đầu.

## 2.6 Thêm GitHub variables và secrets

Trong repo GitHub, mở **Settings → Secrets and variables → Actions**.

Repository variables:

| Tên | Giá trị |
|---|---|
| `AWS_REGION` | Region của bucket và EC2 |
| `ARTIFACT_BUCKET` | Tên bucket |
| `EC2_INSTANCE_ID` | Instance ID mục tiêu cho SSM |

Repository secrets:

| Tên | Giá trị |
|---|---|
| `AWS_ROLE_ARN` | ARN GitHub OIDC role đã tạo ở mục 2.3 |

## 2.7 Hoàn thiện cấu hình DVC trên GitHub

`.dvc/config` phải được commit cùng các file `.dvc`; remote S3 không chứa credentials. Workflow dùng OIDC để `dvc pull` dữ liệu. Sau quality gate, Release job mới upload model và source lên S3 rồi dùng SSM để tải source xuống EC2 và restart service. Đảm bảo con trỏ của `data/train_batch1.csv` và `data/holdout.csv` đã được `dvc push` trước khi Actions chạy.

## 2.8 Chạy pipeline lần đầu

Sau khi hoàn thành Bước 1 và toàn bộ cấu hình cloud:

```bash
git add src tests scripts .github/workflows/cicd.yml requirements.txt params.yaml
git commit -m "feat: implement AWS CI/CD and income API"
git push origin main
```

Trong tab **Actions**, xác nhận các jobs chạy tuần tự **Unit Test → Train → Quality Gate → Release**. `Release` chỉ chạy khi F1 của lớp dương đạt ít nhất `0.65`. Job Train tải report JSON và release bundle thành artifacts; sau Quality Gate, job Release upload model/source lên S3, gọi SSM để cập nhật EC2, restart service và xác nhận `/healthz`.

Từ máy local, thay IP bằng public IPv4 EC2:

```bash
VM_IP=<PUBLIC_IPV4_EC2>
curl "http://$VM_IP:8080/healthz"
curl -X POST "http://$VM_IP:8080/score" \
  -H "Content-Type: application/json" \
  -d '{"features": [60, 2, 5, 2, 4, 0, 1, 0, 0, 45]}'
```

Kết quả mong đợi: `{"status":"ok"}` và một dự đoán với nhãn `thu_nhap_thap` hoặc `thu_nhap_cao`.

## Kết quả cần đạt - Bước 2

- DVC remote S3 hoạt động và data objects hiển thị dưới `dvc/`.
- Bốn GitHub Actions jobs đều xanh; Quality Gate kiểm tra `f1_score >= 0.65`.
- S3 có `artifacts/current/model.joblib`.
- EC2 trả lời đúng ở `/healthz` và `/score`.
- Chụp `02-actions-buoc-2.png`, `04-curl-api.png`, `05-cloud-storage.png` theo [quy cách ảnh](../nop-bai/anh-chup-man-hinh/README.md).

## Xử lý sự cố

- **`AccessDenied` khi DVC pull:** kiểm tra AWS Region, OIDC role ARN/trust subject, và quyền S3 list/get giới hạn đúng prefix `dvc/`.
- **OIDC `Not authorized to perform sts:AssumeRoleWithWebIdentity`:** xác nhận GitHub OIDC provider, audience `sts.amazonaws.com`, subject đúng repo và nhánh `main`; workflow cần `id-token: write`.
- **Upload model thất bại:** xác nhận GitHub role có quyền ghi objects trong `artifacts/current/` và variable `ARTIFACT_BUCKET` đúng.
- **Service không khởi động:** xem `sudo journalctl -u income-api -n 100`; kiểm tra instance profile, Region/bucket trong unit file và model đã có trên S3.
- **SSM command timeout:** xác nhận EC2 role có `AmazonSSMManagedInstanceCore`, SSM Agent đang Online, instance có outbound HTTPS và GitHub role được phép gửi lệnh tới đúng instance.
- **Health check lỗi sau restart:** kiểm tra TCP 8080 inbound từ IP của a và log systemd; workflow thử lại tối đa 60 giây.

Tiếp theo: [Bước 3 - Huấn luyện liên tục](buoc-3.md)
