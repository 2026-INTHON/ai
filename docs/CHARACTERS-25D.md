# Malo 정면용 2.5D 캐릭터

[미리보기](https://inthon-demo-20261031-dh.koreacentral.cloudapp.azure.com/models/) · [카탈로그 JSON](https://inthon-demo-20261031-dh.koreacentral.cloudapp.azure.com/models/catalog.json)

## 구현된 것

고정된 캐릭터 시트에서 텍스처를 추출하고 얕은 메시, 10개 본, 6개 얼굴 변형, 9개 애니메이션을 가진 glTF 2.0 GLB를 제작했습니다. 얼굴을 AI로 매번 다시 그리지 않으며, 파트 색상 변경 시 얼굴 텍스처가 바뀌지 않는지도 빌드에서 확인합니다. glTF 공식 검증 결과 4명 모두 오류·경고 0건입니다.

| 항목 | 내용 |
|---|---|
| 캐릭터 ID | `girlfriend`, `friend`, `manager`, `professor` |
| 파일 | `/models/{id}/{id}.glb` · 약 3.8–5.3 MB/명 |
| 카탈로그 | `/models/catalog.json` · 상대 URL은 이 JSON의 주소를 기준으로 해석 |
| 개별 명세 | `/models/{id}/rig.json` |
| 분리 파트 | `FaceBodyProps`, `Hair`, `Outfit` |
| 얼굴 morph | `blink`, `smile`, `frown`, `browRaise`, `browFurrow`, `mouthOpen` |
| 동작 clip | `idle`, `talk`, `happy`, `confused`, `sad`, `angry`, `nod`, `shake`, `greeting` |
| 색상 미리보기 | 헤어 original/chestnut/black · 의상 original/navy/olive |

## 범위와 제한

- 정면 그림에 깊이와 리깅을 적용한 **2.5D 릴리프 모델**입니다. 옆·뒤가 완성된 입체 모델은 아니며 회전은 좌우 약 8도로 제한합니다.
- 모션은 작은 고개·상체 움직임과 얼굴 변형 중심입니다. 친구의 인사에는 손목 움직임도 포함합니다. 큰 팔 동작·보행·신체 회전은 제작 범위에 없습니다.
- 입 움직임은 단순한 말하기 효과입니다. TTS의 음소별 정밀 립싱크는 구현하지 않았습니다.
- 색상은 시안용 프리셋입니다. 다른 헤어컷·옷 모양은 아직 제공하지 않으며, 별도 파트와 텍스처를 제작해 같은 리깅 규격에 연결해야 합니다. 원본 의상이 기본입니다.
- `KHR_materials_unlit`로 원본의 조명과 색을 보존합니다. 색상 선택에는 `KHR_materials_variants` 처리가 필요하며, 미리보기에 처리 예제가 있습니다.

## AI·Backend 연결

1. 앱은 캐릭터 ID별 GLB를 한 번 로드하고 캐시합니다. 모델은 공유 공개 에셋이며 API 키가 필요하지 않습니다.
2. 기존 대화 평가의 `emotion`을 애니메이션에 대응합니다: `neutral → idle`, 나머지 `happy/confused/sad/angry`는 동명 clip입니다.
3. TTS 재생 시작 때 입 움직임을 켜고, 종료·중단 때 끕니다. 끄덕임·고개 흔들기는 장면에 맞게 선택합니다.
4. 표정·동작 전환에는 이미지 API를 호출하지 않습니다. LLM·STT·TTS 비용은 기존 파이프라인에 따르고, 이 모델의 재생·표정 렌더에는 AI API 비용이 없습니다.

기존 Backend `/api/v1/assets/personas`는 **이전 이미지 카탈로그**입니다. 새 모델 연결에는 `/models/catalog.json`을 사용해야 합니다. Backend 인증·세션·보상 API를 변경하지 않았으며, FE 앱 화면에는 이 변경을 자동 적용하지 않았습니다.

## 앱에 넣을 수 있는 임베드 모드

`/models/?embed=1&character=girlfriend`로 열면 조작 패널 없이 투명한 캐릭터만 표시합니다. WebView가 준비되면 `modelReady` 메시지를 보냅니다. 앱 구현은 FE 팀 작업이며, 아래 메시지 규격과 독립 미리보기만 제공합니다.

```json
{"type":"setCharacter","characterId":"friend"}
{"type":"setEmotion","emotion":"happy"}
{"type":"setGesture","gesture":"nod"}
{"type":"setSpeaking","speaking":true}
```

`window`/`document`의 `message` 이벤트로 JSON 문자열 또는 객체를 받습니다. 지원 값 이외의 명령은 무시합니다. 음성 파일·계정·비밀 키는 이 뷰어로 전달하지 않습니다. 직접 GLB를 렌더링할 경우 WebView 없이 같은 clip과 morph 이름을 사용하면 됩니다. 실제 iPhone/Galaxy 앱 내 성능·브리지 연결은 FE 통합 단계에서 확인해야 합니다.

## 재생성·검증

실행 위치는 AI 저장소 루트입니다. 원본 시트가 달라지면 얼굴·신체 기준점과 파트 마스크도 다시 맞춰야 합니다.

```sh
pip install -r tools/requirements-models.txt
python tools/build_characters_25d.py --source malo_ai/style-reference.png --out assets/models
npm --prefix tools ci
npm --prefix tools run validate
python -m http.server 8787 --bind 127.0.0.1 --directory assets/models
```

`http://127.0.0.1:8787/`에서 확인합니다. HTML 파일을 직접 여는 `file://` 방식은 브라우저 모듈·fetch 제한 때문에 지원하지 않습니다. 미리보기의 표정 묶음 버튼은 같은 모델에서 4명×5표정의 768×1024 투명 PNG를 내보냅니다. 외부 AI 호출은 없습니다. Three.js/fflate는 로컬에 포함하며 라이선스는 `vendor/`에 있습니다.
