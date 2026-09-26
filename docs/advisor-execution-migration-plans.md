# Brainstorm: migrate `advisor-execution` vào Codex Advisor

Ngày: 2026-09-22
Trạng thái: draft brainstorm, chưa có plan nào được duyệt để triển khai
Repo: `D:\Program\Codex-Advisor`

## 1. Yêu cầu của Quang

### Yêu cầu trực tiếp
1. Đọc nhanh chỉ mục codebase tại:
   `D:\Program\Codex-Advisor`.
3. Đọc toàn bộ skill folder
   `C:\Users\lehuu\.codex\skills\advisor-execution`, gồm:
   - `SKILL.md`;
   - `agents/openai.yaml`;
   - `references/advisor-protocol.md`.

### Yêu cầu và bối cảnh rút ra từ chat được chia sẻ

- Mục tiêu là có thể fork/import Advisor cho workspace/tài khoản riêng, không
  mặc nhiên phải publish lên public Plugins Directory.
- Cross-device không đồng nghĩa với public Marketplace. Khả năng chạy trên
  web/mobile/desktop phụ thuộc capability và execution surface của plugin.
- Repo/source Advisor gốc không có `mcp.json` hoặc `.mcp.json`; giới hạn local
  được giải thích bởi cơ chế thực thi Codex-specific/local, không phải do MCP
  declaration.
- Nếu muốn chạy Advisor thật trên ChatGPT web/mobile, chỉ copy một skill local
  là chưa đủ; cần một execution backend được surface đó hỗ trợ.

## 2. Bằng chứng đã đọc

### Skill nguồn

`C:\Users\lehuu\.codex\skills\advisor-execution` định nghĩa:

- Chỉ tự động dùng khi đang thực thi implementation plan đã được user approve;
  standalone/exploratory task chỉ dùng khi user explicit invoke.
- Primary agent cố định là `gpt-5.6-luna` với `reasoning_effort: max`.
- Primary agent là chủ sở hữu duy nhất của implementation, repository changes,
  debugging, testing, plan tracking và final verification.
- Advisor chỉ consultation/read-only, không edit, implement, mutate,
  destructive action hoặc recursive delegation.
- Mỗi checkpoint có tối đa một advisor opportunity trước khi implementation bắt
  đầu; routine/cheap-to-verify work phải skip.
- Mỗi issue bắt đầu ở `gpt-6-astra` / `low`, escalation một chiều:
  `low -> medium -> high -> extra_high`; mỗi effort chỉ một pass, tối đa bốn
  pass, dừng ngay khi đủ.
- Packet phải nhỏ, chỉ phục vụ một uncertainty; advisor không tự đọc repo, gọi
  tool, browse web, nghiên cứu độc lập hoặc delegate.
- Primary phải tự verify mọi khuyến nghị trước khi hành động và chỉ báo cáo
  advisor activity có ảnh hưởng vật chất.

### Repo local sau khi clone

- Plugin chính nằm tại `plugins/advisor/`.
- Skill hiện có là `plugins/advisor/skills/consultation/`.
- Agent profiles hiện có:
  - `advisor-terra.toml`: `gpt-5.6-terra` / `high`;
  - `advisor-sol.toml`: `gpt-5.6-sol` / `high`;
  - `advisor-astra.toml`: explicit-only `gpt-6-astra` / `high`.
- `plugins/advisor/advisor.toml` có đúng hai tier normal:
  - Standard = Terra/high;
  - Specialist = Sol/high.
- `SPEC.md` và `INVARIANTS.md` yêu cầu plugin hiện tại:
  - có đúng một skill `consultation`;
  - root agent giữ architecture, routing, verification và acceptance;
  - advisor consultation zero-tool/read-only;
  - không có MCP server, connector, API key, hosted service hoặc network
    service;
  - chỉ hỗ trợ transport local Codex CLI/Codex desktop;
  - generic ChatGPT không có local transport thì phải trả
    `route: unavailable` fail-closed.
- `plugins/advisor/scripts/run-advisor.sh` và các inspector là transport local
  có runtime evidence, sandbox, parent/child thread và schema checks; đây không
  phải là một cloud backend.
- `verify.sh --static` là canonical gate và đang bảo vệ nhiều assumption cứng
  về role, tier, schema, installer, receipts và release boundary.

## 3. Xung đột cần giải quyết trước khi migrate

| Vấn đề | Skill `advisor-execution` | Repo hiện tại | Hệ quả |
|---|---|---|---|
| Primary profile | Luna/max | Host/root hiện hành, không do plugin ép được | Chỉ ghi model trong prompt không chứng minh được runtime identity |
| Advisor profile | Astra/low, bounded escalation | Terra/high, Sol/high, Astra/high | Không được âm thầm tái dùng `advisor-astra` vì khác effort |
| Activation | Approved-plan execution, explicit cho standalone | `consultation` implicit cho material decision | Dễ tự động kích hoạt nhầm execution workflow |
| Cardinality | Một opportunity/checkpoint, không retry cùng level | Một consultation theo decision, wrapper có response retry riêng | Phải tách budget/semantics, không gộp mơ hồ |
| Output protocol | Assessment/Why/Challenge/Next action/Risks/Verification/Escalation | Schema response + canonical `ADVISOR RESPONSE` của plugin | Cần adapter/schema riêng hoặc contract mapping rõ |
| Surface | Cần execution host và advisor spawn | Local Codex shell/app-server | Migrate skill không tự tạo được mobile/web execution |
| Packaging | Skill cá nhân có ba file | Manifest/spec hiện nói chỉ có một skill | Thêm skill sẽ buộc sửa manifest, verifier, docs và release contract |

## 4. Nguyên tắc chung cho mọi plan

1. Không đổi `consultation` hiện có cho tới khi có acceptance test chứng minh
   không regression.
2. Không map Astra/low vào Astra/high và không dùng parent-model inheritance.
3. Không tuyên bố mobile/web execution nếu chỉ có bằng chứng từ local CLI/Desktop.
4. Mọi unavailable/unsupported surface phải fail-closed, không fallback im lặng.
5. Primary agent vẫn là authority cho code, runtime, tests, verification và
   accept/reject advice.
6. Không đưa secrets, credentials, raw prompts, raw answers hoặc session IDs vào
   packet, journal, fixture hay release artifact.
7. Mọi plan phải có static tests, contract tests và runtime evidence boundary;
   synthetic/mock evidence không được báo là live compatibility proof.
8. Chưa publish, push hoặc cài vào Codex home live trong giai đoạn brainstorm.

## 5. Các plan khả thi

### Plan A — Dual-skill local plugin, giữ nguyên consultation hiện tại

#### Mục tiêu

Thêm `advisor-execution` như một skill explicit thứ hai trong plugin, giữ
`consultation` là luồng automatic pre-decision hiện tại. Đây là phương án cân
bằng nhất nếu mục tiêu trước mắt là migrate đúng policy của skill vào repo và
không phá runtime Advisor đang có.

Plan này đáp ứng đầy đủ local Codex CLI/Desktop. Nó **chưa** đáp ứng việc chạy
advisor thật trên ChatGPT web/mobile.

#### Thứ tự bước thực hiện

1. Chốt capability matrix và acceptance contract cho hai skill; ghi rõ
   `consultation` và `advisor-execution` là hai lifecycle khác nhau.
2. Chạy baseline hiện tại: `plugins/advisor/scripts/verify.sh --static`, test
   Python và kiểm tra `git status`; lưu kết quả làm mốc, không sửa code.
3. Thêm nguyên bản có kiểm soát vào
   `plugins/advisor/skills/advisor-execution/`:
   `SKILL.md`, `agents/openai.yaml` và `references/advisor-protocol.md`.
4. Chỉnh metadata mô tả activation boundary: execution chỉ chạy sau
   implementation plan đã được user approve; không để implicit matching của
   `consultation` kích hoạt execution workflow.
5. Thêm một role riêng cho execution advisor, ví dụ
   `advisor-execution-astra`, pin chính xác `gpt-6-astra` / `low` / read-only /
   zero-tool. Không sửa hoặc tái sử dụng role Astra/high hiện có.
6. Mở rộng transport theo một route cố định cho execution advisor. Route phải
   freeze model/effort ở đầu issue, giữ one-chain-per-checkpoint và kiểm soát
   `low -> medium -> high -> extra_high`; mọi retry cùng level, parallel
   advisor, recursive delegation và silent fallback đều bị từ chối.
7. Quyết định và triển khai adapter giữa protocol của skill và runtime envelope
   hiện tại: hoặc thêm schema/receipt riêng cho execution, hoặc chứng minh một
   mapping không mất trường `ESCALATION_REQUEST`, acceptance checks và
   disposition. Không trộn nó vào schema consultation nếu làm mất semantics.
8. Cập nhật `plugin.json`, `SPEC.md`, `INVARIANTS.md`, `README.md`,
   `docs/public-directory-compatibility.md` và operations docs để phản ánh
   plugin có hai skill, hai activation contract và local-only boundary.
9. Bổ sung static fixtures/unit tests cho: explicit activation, approved-plan
   gate, primary ownership, exact model/effort, one advisor opportunity per
   checkpoint, escalation ordering, no same-level retry, zero tools, no
   recursion, unavailable parent/surface và redaction.
10. Bổ sung packaging/install tests để plugin local marketplace cài được cả hai
    skill mà không cài live vào Codex home ngoài ý muốn.
11. Chạy lại canonical static gate, unit tests và package inspection; chỉ sau
    khi tất cả pass mới lập kế hoạch attended runtime smoke trên Codex CLI/Desktop.
12. Runtime smoke phải kiểm tra child thread, exact model/effort, read-only,
    zero-tool và receipt thật; không dùng output mock/Inspector đơn lẻ làm bằng
    chứng live.

#### Ưu điểm

- Giữ blast radius nhỏ: consultation hiện tại vẫn là contract riêng.
- Migrate gần sát skill nguồn, dễ audit và dễ bật/tắt bằng explicit invocation.
- Có thể dùng private/local marketplace mà chưa cần public publication.

#### Rủi ro và điều kiện dừng

- Manifest/spec hiện yêu cầu một skill; đây vẫn là thay đổi release contract,
  không phải copy file đơn giản.
- Plugin không thể tự ép root model thành Luna/max nếu host không cung cấp
  model identity đó; phải có preflight/acceptance check hoặc ghi rõ đây là
  desired profile chứ không phải proof.
- Nếu không tạo được route Astra/low có runtime evidence thật, dừng ở
  `unavailable`, không fallback Astra/high/Terra/Sol.

### Plan B — Unified skill/mode trong một plugin

#### Mục tiêu

Giữ plugin chỉ có một skill, nhưng mở rộng `consultation` thành hai mode rõ
ràng: `pre-decision consultation` và `approved-plan execution`. Đây là phương án
phù hợp nếu ưu tiên UX một entrypoint và muốn giữ invariant “một skill”, nhưng
blast radius và nguy cơ regression cao hơn Plan A.

#### Thứ tự bước thực hiện

1. Viết mode contract trước: trigger, owner, allowed phase, advisor budget,
   model/effort, packet schema, receipts và terminal states của từng mode.
2. Giữ nguyên route/receipt của consultation làm compatibility baseline; không
   đổi semantics của Standard/Specialist trong bước đầu.
3. Tạo execution route riêng trong config/transport, pin Astra/low và không cho
   route normal chọn nó.
4. Refactor `SKILL.md` và `references/operations.md` thành phần chung + hai
   mode; mô tả rõ execution không implicit invoke cho standalone và không biến
   thành final review/implementation delegate.
5. Thêm protocol/schema/receipt execution riêng hoặc một versioned envelope có
   discriminator; bảo đảm parser consultation không chấp nhận nhầm execution
   response và ngược lại.
6. Thêm parent-model/parent-runtime preflight để xác định Luna/max khi contract
   yêu cầu; nếu không chứng minh được thì trả unavailable hoặc yêu cầu host
   configuration, không tự đổi model.
7. Mở rộng inspector/audit để tách consultation metrics và execution metrics;
   không gộp usage/budget khiến một route che khuất route kia.
8. Viết regression fixtures cho toàn bộ trigger consultation hiện có, sau đó
   thêm execution fixtures theo từng checkpoint và escalation level.
9. Cập nhật static verifier, release docs, privacy docs, marketplace text và
   recovery guidance.
10. Chạy toàn bộ static/unit tests; sau đó mới làm live smoke riêng cho từng
    mode và xác nhận receipt/transport bằng runtime evidence.

#### Ưu điểm

- Giữ một plugin/skill identity và giảm nguy cơ người dùng cài nhầm package.
- Có thể chia sẻ các primitive chung như packet redaction, runtime inspection,
  terminal handoff và audit.

#### Rủi ro và điều kiện dừng

- Hai lifecycle khác nhau dễ bị implicit matching hoặc receipt semantics làm
  lẫn.
- `verify.sh`, `SPEC.md`, `INVARIANTS.md`, audit và release docs hiện đều giả
  định consultation-centric; thay đổi sẽ rộng.
- Nếu execution mode buộc phải dùng nhiều exception trong một skill, quay lại
  Plan A thay vì làm một “god skill”.

### Plan C — Tách policy core và nhiều execution adapter để đạt cross-device

#### Mục tiêu

Tách phần policy/protocol của `advisor-execution` khỏi transport. Local Codex
adapter tiếp tục dùng runtime hiện tại; một adapter cloud/app-backed riêng mới
có thể phục vụ web/mobile khi surface đó thật sự hỗ trợ. Đây là plan duy nhất
có khả năng đáp ứng **execution cross-device thực sự**, nhưng là một dự án kiến
trúc mới, không phải skill migration thuần túy.

#### Thứ tự bước thực hiện

1. Xác nhận yêu cầu surface bằng tài liệu/channels chính thức hiện hành: web,
   iOS/Android, desktop và Codex; không suy luận rằng universal directory đồng
   nghĩa với universal runtime.
2. Chốt data-flow và threat model: packet nào được gửi ra ngoài local host,
   consent nào cần có, auth/token nằm ở đâu, retention/logging thế nào và dữ
   liệu nào phải redact.
3. Định nghĩa transport-neutral interface gồm `preflight`, `invoke`, `inspect`,
   `classify`, `render receipt` và `unavailable`; contract chung phải giữ
   primary ownership, advisor read-only, zero-tool và bounded escalation.
4. Đóng gói policy core `advisor-execution` thành phần không phụ thuộc shell,
   `CODEX_HOME`, persisted rollout hoặc `require_escalated`.
5. Giữ local Codex adapter làm implementation đầu tiên, map runtime evidence
   thật vào interface và không đổi thành cloud fallback.
6. Chỉ sau khi có capability/authorization rõ ràng, thiết kế cloud/app-backed
   adapter cho web/mobile. Nếu cần MCP/connector/hosted service, cập nhật
   invariant “no MCP/hosted service” thành một contract mới và xin review riêng.
7. Thiết kế authentication, authorization, user consent, rate/budget limits,
   privacy notice và failure isolation cho adapter remote; không gửi auth file,
   session material hoặc raw conversation ngoài boundary đã duyệt.
8. Dùng cùng response schema nhưng tách runtime evidence theo adapter; không coi
   receipt từ cloud là bằng chứng local Codex và ngược lại.
9. Viết contract tests cho mọi adapter, negative tests cho capability thiếu,
   network failure, expired auth, non-read-only backend, tool-use và malformed
   response; live test từng surface có bằng chứng thực tế.
10. Cập nhật manifest/capabilities, marketplace/private distribution, privacy,
    support, release và recovery docs; công bố rõ surface nào supported,
    unavailable hay experimental.
11. Chỉ khi có live evidence trên web/mobile mới tuyên bố cross-device; nếu
    không, giữ `route: unavailable` trên surface đó.

#### Ưu điểm

- Tách đúng policy của skill khỏi giới hạn local transport.
- Có đường kiến trúc rõ để mở rộng web/mobile mà không giả vờ rằng local shell
  chạy được ở mọi nơi.

#### Rủi ro và điều kiện dừng

- Cần authority/backend/capability mới ngoài repo hiện tại.
- Tăng mạnh scope về security, privacy, auth, cost, availability và release.
- Không được bắt đầu implementation chỉ dựa trên giả định rằng một plugin
  private tự động có quyền chạy remote code hoặc tạo persistent access.

### Plan D — Companion skill trong repo, chưa đưa vào plugin package

#### Mục tiêu

Đặt skill vào một khu vực project-local, ví dụ
`.agents/skills/advisor-execution/`, giữ plugin `advisor` và marketplace contract
hoàn toàn nguyên trạng. Đây là phương án staging nhanh nhất nếu cần kiểm chứng
workflow trước khi quyết định có biến nó thành plugin skill hay không.

#### Thứ tự bước thực hiện

1. Xác nhận project-local skill discovery của Codex trên host mục tiêu.
2. Copy ba file skill nguồn vào `.agents/skills/advisor-execution/`, giữ nguyên
   profile/contract; chỉ sửa path reference nếu test discovery yêu cầu.
3. Ghi rõ skill này không thuộc `plugins/advisor/.codex-plugin/plugin.json` và
   không được quảng cáo như capability của marketplace plugin.
4. Chạy validator/discovery test trong repo và một manual dry run không spawn
   advisor để kiểm tra activation boundary.
5. Nếu workflow cần runtime transport, quay lại Plan A/B; nếu cần mobile/web,
   chuyển sang Plan C.

#### Ưu điểm

- Không phá plugin hiện tại, verifier hoặc public release contract.
- Phù hợp để kiểm chứng wording, trigger và packet protocol trước.

#### Hạn chế

- Không tự có trong private marketplace import.
- Có thể không được discover trên mọi surface; phải chứng minh project-local
  skill support bằng host evidence.

## 6. Khuyến nghị sơ bộ

1. Nếu mục tiêu ngắn hạn là migrate skill vào repo mà vẫn bảo toàn Advisor hiện
   tại: chọn **Plan A**, nhưng triển khai theo từng checkpoint và coi exact
   Astra/low + Luna/max là acceptance gates, không phải wording trong prompt.
2. Nếu ưu tiên giữ một skill identity hơn mức cô lập runtime: cân nhắc **Plan B**,
   chỉ sau khi có design review chứng minh hai mode không thể kích hoạt nhầm.
3. Nếu “dùng được trên web/mobile” là yêu cầu bắt buộc cho execution thật: chọn
   **Plan C**; Plan A/B chỉ là local foundation và không đủ.
4. Nếu Quang chỉ muốn kiểm chứng policy trước, chọn **Plan D** làm spike/staging,
   rồi quay lại A hoặc C sau khi có host evidence.

Khuyến nghị triển khai thực tế là **D -> A -> C (nếu cross-device là bắt buộc)**.
Plan B chỉ nên được chọn khi một entrypoint duy nhất là yêu cầu quan trọng hơn
blast-radius và khả năng audit độc lập của hai workflow.

## 7. Các quyết định cần Quang duyệt trước khi viết implementation plan

1. Cross-device web/mobile là hard requirement cho execution thật hay chỉ là
   mong muốn phân phối skill?
2. `gpt-5.6-luna/max` cho primary và `gpt-6-astra/low` cho advisor có phải là
   exact runtime requirement không, hay cho phép host-specific adapter miễn
   không silent substitute?
3. Có cho phép thêm MCP/connector/hosted backend và thay đổi privacy/data-flow
   contract hiện tại không?
4. Muốn skill nằm trong marketplace plugin (`Plan A/B`) hay chỉ project-local
   companion trước (`Plan D`)?
5. Có chấp nhận tách migration thành hai phase: local contract trước, cross-device
   backend sau không?

## 8. Trạng thái hiện tại
- File này là brainstorm record; cần user review/agent chọn hướng trước khi chuyển sang design spec hoặc implementation plan chi tiết.
