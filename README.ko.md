# WiFi 차단 진단 도구

이 저장소에는 네트워크 차단이 어디에서 발생하는지 식별하는 데 도움이 되는 작은 Python 진단 도구들이 들어 있습니다.

도구 범위는 의도적으로 진단에만 한정됩니다:
- DNS 해석 실패
- TCP 또는 TLS 도달 가능 여부
- DNS 또는 STUN 같은 UDP 응답 프로토콜

이 도구들은 패킷 스푸핑, 단편화, 방화벽 우회 기능을 구현하지 않습니다.

## 파일

- `tcp.py`: DNS, TCP/TLS, UDP 응답기, 정확한 HTTP URL 검사를 실행하는 메인 진단 도구
- `UDP.py`: 빠른 테스트용 UDP DNS 전용 진단 도구
- `agent.md`: 현재 제품 방향, 아키텍처 메모, 검증 규칙

## 요구 사항

- Python 3.11 이상
- 스크립트를 실행하는 시스템에서 외부 네트워크에 접근 가능해야 함

## 사용법

기본 테스트 세트를 실행합니다:

```powershell
python tcp.py
```

기본 세트는 `targets.json`에서 불러오며 다음 대상이 포함됩니다:
- GitHub와 Discord
- Riot Games, League of Legends, VALORANT
- Steam Store와 Steam Community
- Epic Games Store
- Blizzard와 Battle.net
- Nexon과 MapleStory
- UDP DNS 및 STUN 검사

타임아웃을 늘립니다:

```powershell
python tcp.py --timeout 5
```

단일 호스트를 테스트합니다:

```powershell
python tcp.py --host github.com --port 443 --check tls --name "GitHub TLS"
```

배포된 특정 페이지 URL을 정확히 테스트합니다:

```powershell
python tcp.py --url https://jsk1004ha.github.io/CHRONO-BREAK/ --name "CHRONO-BREAK"
```

게임 관련 사이트 예시:

```powershell
python tcp.py --host www.leagueoflegends.com --port 443 --check tls --name "LoL Site"
python tcp.py --host playvalorant.com --port 443 --check tls --name "VALORANT Site"
python tcp.py --host shop.battle.net --port 443 --check tls --name "Battle.net Shop"
python tcp.py --host maplestory.nexon.com --port 443 --check tls --name "MapleStory"
```

원시 출력을 저장합니다:

```powershell
python tcp.py --json report.json
```

네트워크 라벨과 함께 CSV 출력을 저장합니다:

```powershell
python tcp.py --network-label school_wifi --csv report.csv
```

UDP DNS 진단을 직접 실행합니다:

```powershell
python UDP.py --server 8.8.8.8 --port 53 --query-name github.com
```

## 상태 가이드

- `OPEN`: 진단이 성공적으로 완료됨
- `DNS_FAIL`: 네트워크 진단 전에 호스트명 해석에 실패함
- `TIMEOUT`: 타임아웃 시간 안에 응답이 오지 않음
- `REFUSED`: 원격 엔드포인트가 연결을 명시적으로 거부함
- `TLS_FAIL`: TCP 연결은 열렸지만 TLS 협상이 실패함
- `OS_ERROR`: 로컬 소켓 스택이 시스템 오류를 반환함
- `ERROR`: 예기치 않은 오류가 발생함

## 결과 해석

- `DNS_FAIL`은 보통 로컬 DNS 문제, DNS 가로채기, 또는 잘못된 호스트명을 의미합니다.
- `tls` 검사에서 `TIMEOUT`은 상위 필터링, 패킷 손실, 느린 경로를 뜻할 수 있습니다. 이것만으로 차단을 단정할 수는 없습니다. 호스트가 여러 IPv4 주소로 해석될 때 이 도구는 이제 해석된 모든 IP가 타임아웃되었는지도 함께 보고합니다.
- UDP에서의 `TIMEOUT`은 단지 응답이 관측되지 않았다는 뜻입니다. 많은 UDP 서비스는 알 수 없는 페이로드를 무시하므로, 최종 결론이 아니라 단서로 해석해야 합니다.
- `github.com`, `raw.githubusercontent.com`, 자체 호스팅 사이트 사이의 `tls` 결과를 비교하는 편이 단일 대상만 테스트하는 것보다 더 유용한 경우가 많습니다.

## 참고

- 기본 대상 목록은 예시이며 `targets.json`에서 변경할 수 있습니다.
- GitHub Pages 또는 배포된 정적 사이트 차단 여부를 확인할 때는 정확한 페이지/경로 검사를 위해 `--url`을, 순수 TCP/TLS 도달 가능 여부만 보려면 `--host`를 사용하는 것이 좋습니다.
- 데스크톱 진단 앱의 현재 설계 방향은 `agent.md`에 문서화되어 있습니다.
