# 서버 배포 (Oracle Cloud Ubuntu 기준)

디스코드 봇은 서버에서 밖으로 나가는 연결만 사용하므로 방화벽 포트를 열 필요가 없습니다.

## 1. 파일 올리기 (내 PC에서)

```powershell
scp -i <키파일> -r bot.py main.py dorm_menu.py requirements.txt .env deploy ubuntu@<서버IP>:~/contest_alert/
```

`.venv`, `contest.db`, `temp.html`은 올리지 않아도 됩니다. DB는 서버에서 처음 실행할 때 새로 만들어집니다.

## 2. 서버에서 설치

```bash
sudo apt update && sudo apt install -y python3 python3-venv
cd ~/contest_alert
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod 600 .env
```

직접 실행해서 로그인되는지 먼저 확인합니다 (Ctrl+C로 종료):

```bash
.venv/bin/python bot.py
```

## 3. 24시간 실행 (systemd)

사용자 이름이 `ubuntu`가 아니면 `deploy/contest-bot.service`의 `User`와 경로를 먼저 고쳐 주세요.

```bash
sudo cp deploy/contest-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now contest-bot
```

서버가 재부팅되거나 봇이 죽어도 자동으로 다시 실행됩니다.

## 자주 쓰는 명령

```bash
sudo systemctl status contest-bot     # 상태 확인
journalctl -u contest-bot -f          # 실시간 로그
sudo systemctl restart contest-bot    # 코드 수정 후 재시작
```
