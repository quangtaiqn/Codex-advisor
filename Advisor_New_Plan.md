# Advisor_New_Plan — Astra routing trên plugin Codex hiện có

> Revision 10 — 2026-09-27. CP0–CP6 COMPLETE; bổ sung qualification runtime CP4/CP5 trên Desktop và CLI, cùng xác minh hardening an toàn sau plan và sửa hai lệch nhỏ do final review phát hiện.
> Trạng thái: CP0–CP6 COMPLETE; CP4/CP5 PASS theo tiêu chí synthetic escalation qualification và cold start. Issue thực được xác minh dừng ở Astra/Low; qualification tổng hợp chạy runtime đủ Low → Medium → High → Extra High trên cả hai host. Không claim issue thực cần escalation qua cả ladder hoặc có tiết kiệm token.
> Primary agent thực hiện inline theo executing-plans; advisor theo advisor-execution; final review theo final-review.

**Goal:** Giữ plugin Advisor đang chạy trên Codex, thay cơ chế chọn advisor bằng Astra Low → Medium → High → Extra High và chỉ consultation tại checkpoint thực sự cần thiết.

**Architecture:** Giữ skill consultation → run-advisor.sh → Codex child read-only → runtime inspectors → schema validation → receipt như repo hiện có. Chỉ thay activation/routing, escalation và kiểm soát lượt gọi liên quan.

**Tech stack:** POSIX shell, Python, JSON Schema, TOML và tests hiện có. Không thêm backend, API billing, database hoặc app connector.

**Spec:** Policy nguồn tại C:\Users\lehuu\.codex\skills\advisor-execution gồm SKILL.md, references/advisor-protocol.md, agents/openai.yaml; yêu cầu mới nhất của Quang ưu tiên hơn các phương án cũ.

## 1. Cách mình sẽ thực hiện

1. Chụp baseline và kiểm tra plugin hiện có.
2. Đưa policy activation từ skill của Quang vào skill consultation của plugin.
3. Thay selector cũ bằng Astra cố định, Low đầu tiên và escalation tuần tự.
4. Giữ launcher và inspector, bổ sung validation escalation cùng trạng thái lượt gọi tối thiểu để resume không gọi lại.
5. Test routing, budget và regression; kiểm tra runtime thật có kiểm soát.
6. Review, bàn giao và ghi checkpoint có thể resume/rollback.

Kết quả mong muốn là plugin hiện tại chạy theo policy mới. Bản plan này bỏ hoàn toàn yêu cầu xây execution cloud/app-backed.

## 2. Phạm vi thay đổi

### Giữ nguyên

- Codex CLI/Desktop execution, authentication đang có và installed-plugin launcher boundary.
- Read-only child, zero-tool checks, parent/child identity và provenance inspection.
- Packet qua stdin, private transport directory, cleanup, cancellation và deadline đang có.
- Quy trình drain session_id đến terminal exit rồi kiểm tra envelope.
- Root ownership, final-review riêng, cách thu usage và journal opt-in.
- Marketplace identity, install flow, assets, website và các tính năng không liên quan routing.
- Skill cá nhân trong Codex home; plan chỉ thay bản policy trong repo plugin.

### Thay đúng phần cần thiết

- Standard/Terra, Specialist/Sol và alias Astra/high cố định không còn là active routing.
- Normal consultation bắt đầu Astra/low; effort kế tiếp chỉ từ chain state và escalation hợp lệ.
- Trigger trong consultation/SKILL.md dùng checkpoint preflight của advisor-execution.
- Bỏ completion consultation tự động, fresh follow-up chain cùng checkpoint và inference retry cùng effort để sửa schema.
- Schema/test/docs được sửa tối thiểu để thể hiện escalation và budget mới.
- Role/config/installer/audit chỉ thay pin hoặc nhãn thực sự phụ thuộc routing; không refactor rộng.

## 3. Policy đích

### Khi nào advisor can thiệp

- Approved-plan execution: primary preflight trước mỗi checkpoint.
- Chỉ consult nếu còn uncertainty khó giải quyết bằng đọc code/test nhanh VÀ sai quyết định sẽ có cost/risk đáng kể.
- Standalone: chỉ xét advisor khi Quang explicit yêu cầu; vẫn phải có bounded question và gate phù hợp.
- Routine, formatting, factual/status, quyết định đã rõ, cheap checks đủ → skip, không spawn.
- Mỗi checkpoint chỉ một opportunity trước implementation. Khi implementation đã bắt đầu, lỗi thông thường do primary xử lý.
- Không consultation chỉ vì sắp hoàn tất, muốn reassurance hoặc đã từng dùng advisor.
- Materially new issue cần evidence và scope mới thật; không đổi tên checkpoint để reset budget.
- Primary model Luna/max là contract của workflow nguồn. Plugin không đổi model của main chat: ghi yêu cầu ở execution entrypoint và báo mismatch nếu host có bằng chứng khác. Việc chuyển primary profile là host configuration, không biến plugin thành implementation router.

### Model và effort

| Mức policy | Model | Giá trị gửi Codex runtime |
|---|---|---|
| low | gpt-6-astra | low |
| medium | gpt-6-astra | medium |
| high | gpt-6-astra | high |
| extra_high | gpt-6-astra | xhigh, sau kiểm chứng host |

Giữ tên extra_high của skill trong protocol; adapter ánh xạ minh bạch sang xhigh đang được enum config repo hỗ trợ. CP0/CP3 kiểm tra CLI/inspector thực tế; nếu không hỗ trợ thì unavailable, không đổi sang high/max/ultra.

Không parent-model inheritance, model fallback, preset override hoặc start trực tiếp Medium/High. Inspector phải nhận expected model và expected effort của pass cụ thể, so với runtime evidence thật.

### Escalation

- Valid response đủ giải quyết → dừng.
- Chỉ ESCALATION_REQUEST hợp lệ với next level liền kề, unresolved difficulty, reason và required resolution mới có thể escalate.
- Primary verify request có thực sự là thiếu reasoning; thiếu facts thì thu evidence, không tăng effort tự động.
- Mỗi effort một child; tối đa bốn children/chain. Đủ ở Low thì chỉ một.
- Ở Extra High luôn dừng và báo limitations.
- Invalid JSON/schema, timeout, wrong model/effort, tool-use, isolation hoặc missing runtime evidence → unavailable, không retry/escalate.
- Tắt corrective inference retry cùng effort trong wrapper. Semantic validation và redacted failure vẫn giữ nguyên.

## 4. Hạn chế burn token

1. Cheap primary preflight, không gọi thêm model để quyết định có cần advisor.
2. Skip routine và bỏ automatic completion consultation.
3. Một chain/checkpoint, mỗi level một pass, tối đa bốn; ngừng ngay khi đủ.
4. Compact packet theo skill: objective, checkpoint, intended approach, uncertainty, relevant evidence, previous attempts cần thiết, hypothesis và impact. Không gửi full history/full diff.
5. Escalation chỉ gửi packet hiện tại cùng tóm tắt ngắn kết quả trước và evidence mới cần thiết; không nối toàn bộ transcripts.
6. Giữ response ngắn với schema fields hiện có; không thêm tutorial hoặc lời nhắc lặp.
7. Resume đọc state cũ, không mở chain mới. Timeout chưa biết outcome không resubmit.
8. Giữ usage journal opt-in và null/partial semantics; không cộng reasoning/cached input hai lần.
9. Không hứa hard token cap nếu Codex CLI hiện tại không hỗ trợ. V1 cưỡng chế số lần gọi và chặn lặp; deadline/packet size là giới hạn bổ sung, không bảo đảm tuyệt đối số token suy luận.
10. Đo usage thực tế khi canary; không claim phần trăm tiết kiệm bằng mock.

Skill nguồn không đặt giới hạn byte/token cố định. Giữ các giới hạn kỹ thuật hiện có của repo và quy tắc compact context trong skill; không tự thêm các mức 16 KiB/6 KiB hoặc quota mới. Cơ chế tiết kiệm chính là chọn đúng lúc consult, một pass mỗi effort và dừng ngay khi đủ.

## 5. Thay đổi file có giới hạn

| File | Thay đổi dự kiến |
|---|---|
| plugins/advisor/skills/consultation/SKILL.md | Activation theo approved-plan, checkpoint và stop conditions nguồn |
| .../references/operations.md, .../agents/openai.yaml | Hướng dẫn chain mới, metadata đồng bộ |
| plugins/advisor/advisor.toml | Một Astra policy, ordered levels; bỏ selection theo tier |
| plugins/advisor/scripts/advisor_config.py | Resolve Astra pass; reject legacy model override trong active path |
| plugins/advisor/scripts/run-advisor.sh | Giữ transport; lấy selection từ chain; một child/pass; bỏ schema retry |
| plugins/advisor/advisor-response.schema.json | Bổ sung escalation typed; giữ bảy field nội dung đang có |
| plugins/advisor/scripts/advisor_chain.py (mới, nhỏ) | Durable state, level reservation và resume; không làm transport |
| plugins/advisor/agents/*.toml | Bỏ Terra/Sol active routing; Astra profile mặc định low, wrapper truyền explicit effort |
| plugins/advisor/scripts/install-agents.sh | Điều chỉnh inventory tối thiểu nếu role inventory đổi; backup byte-exact, không overwrite custom file |
| settings.schema.json, models.json | Cập nhật phần selectors phụ thuộc policy; giữ unrelated usage settings |
| evals/trigger-cases.json, tests/test_advisor_*.py, scripts/verify.sh | Regression và routing fixtures mới |
| scripts/advisor-audit.sh | Chỉ cập nhật role/chain/effort counts cần thiết, giữ redaction |
| README.md, SPEC.md, INVARIANTS.md, docs/model-configuration.md | Đồng bộ contract routing, retry và activation |
| docs/advisor-routing-progress.md, docs/routing-checkpoints/ | Implementation progress và immutable receipts |

Trước mỗi edit, chứng minh file có dependency với policy mới. Nếu file không cần thay thì giữ nguyên. Không thêm repo companion skill trùng tên; entrypoint packaged hiện tại tiếp tục là consultation.

## 6. Contract tối thiểu cho escalation và resume

### Output và envelope

Giữ recommendation, why, strongest_objection, change_my_mind, acceptance_checks, risks, follow_up_areas.
Bổ sung escalation object:
- next_level: null | medium | high | extra_high.
- reason, unresolved_difficulty, required_resolution: strings.
- next_level=null nghĩa là dừng; lý do có thể đủ evidence, cần facts hoặc đã đạt trần.
- next_level khác null phải có ba trường giải thích nonblank và đúng immediate next.

Wrapper kiểm tra bằng schema + semantic validation; model không tự ghi runtime metadata. Giữ canonical receipt tám dòng nếu consumer cần; escalation đọc từ field riêng trong verified envelope. Kiểm tra strict consumers để quyết định version bump khi implementation; không silently đưa schema mới cho parser cũ.

Adapter schema phải giữ đủ bảy ý của protocol nguồn: Assessment (kèm calibrated confidence), Why, Challenge, Next check/action, Risks/alternatives, Verification và Escalation. Mapping sang các field repo phải được test; nếu field hiện có không biểu đạt đủ confidence hoặc next action thì bổ sung tối thiểu, không bỏ mất nội dung để giữ nguyên hình thức receipt. Read-only/no-recursion là yêu cầu skill; zero-tool là bảo đảm mạnh hơn đã có của repo và tiếp tục được giữ.

### Chain state cục bộ

Tận dụng private Codex-home state pattern hiện có, tách safety ledger khỏi optional usage journal. Journal có thể off nhưng budget vẫn phải được ghi.

State chứa opaque task/checkpoint key, chain ID, policy hash, packet digest, reserved/completed levels, status, implementation_started và next_action. Không lưu prompts/answers vào audit; nếu cần giữ valid result để resume, dùng private short-lived artifact và chỉ lưu reference trong state.

- Một checkpoint key đã consumed không được tạo chain mới.
- Atomic lock + write-to-temp + replace theo pattern hiện có; permissions owner-only, reject symlink/nonregular paths.
- Reserve level trước launch, mark completed sau inspected result.
- Crash/timeout sau reserve: reconcile child/result hiện có; nếu chưa chứng minh có launch hay không, mark uncertain và không respawn cùng level.
- Nếu process còn chạy, drain đúng handle/owned process; session handle hết hiệu lực thì dùng persisted evidence, không launch replacement.
- Safety state phải bền qua session restart; không xóa consumed markers khi journal clear/prune.
- Runtime state hoàn tất khác với Git checkpoint hoàn tất.

## 7. Phases và todo

### Phase 0 / CP0 — Baseline

**Goal:** Có nguồn chuẩn và điểm quay lại trước migration.
- **Status: COMPLETE — 2026-09-23.** Fresh canonical static gate and sequential unit rerun pass.
- [x] Kiểm tra repo root, AGENTS.md áp dụng, git status/HEAD và file user đang sửa.
- [x] Đọc ba file skill nguồn; ghi hash để không áp dụng policy cũ từ memory.
- [x] Chạy sh plugins/advisor/scripts/verify.sh --static tại repo root; ghi output/exit, missing dependency là unavailable.
- [x] Đọc signatures/fixtures của selector, wrapper, inspectors và schema consumers; xác định enum effort CLI đang hỗ trợ.
- [x] Tạo branch codex/advisor-astra-routing khi thực thi; ghi baseline SHA và owned paths.
- [x] Tạo progress CP0..CP6 và receipt baseline.
**Acceptance:** baseline được ghi, không tự diễn giải source test thành live proof.
**Verification evidence (2026-09-23):**
- Repo root `D:/Program/Codex-Advisor`; branch `codex/advisor-astra-routing`; baseline SHA `7494786b9aef8c7d375ed9925beef8e46392811b`; HEAD tại lần xác minh `f5c76f383ec949b349baf1a978c4a2bbaf1a6bd7`. Không tìm thấy `AGENTS.md` bên trong repo; áp dụng hướng dẫn AGENTS được cung cấp cho task. Đã kiểm tra và giữ nguyên working-tree WIP.
- SHA-256 skill nguồn: `SKILL.md` = `48BBCEC5C6937CF49130B4F5EC50588B02CF5BA07ED214FB847340A86EDA7260`; `references/advisor-protocol.md` = `66AB8CBB4ED82DDB9053D59DC67DEA63BFE3F98721AAA3FF5B4FE7E6628146D0`; `agents/openai.yaml` = `0570BEEBFB9ACBC2C729D15F2A29C9E0855D4B3DC67FDF48FC22673D59575ABD`.
- `sh plugins/advisor/scripts/verify.sh --static` (WSL, repo root): exit 0; `VERIFY PASSED: Advisor 1.4.5 consultation-only static contract`; embedded Advisor suite 82/82 and candidate-package suite 30/30 pass.
- `python3 -m unittest discover -s plugins/advisor/tests -p 'test_*.py'` (WSL, chạy tuần tự): exit 0, 82/82 pass. Một lần chạy đồng thời trước đó có 1 failure ở cancellation-cleanup assertion; test đó chạy riêng 1/1 pass và lần chạy tuần tự toàn suite pass. Không sửa code trong lượt xác minh này.
- `npm test -- --reporter=line` (`web-tests`): exit 0, Playwright 52/52 pass. Đây là regression evidence bổ sung, không phải live advisor-runtime proof.
**Rollback:** chưa có thay đổi behavior.

### Phase 1 / CP1 — Activation theo skill nguồn

**Goal:** Advisor chỉ vào đúng checkpoint.
**Status: COMPLETE** — receipt: `docs/routing-checkpoints/CP1.json`.
- [x] Viết fixtures routine→skip, explicit standalone+uncertainty→consult, unrequested standalone→skip.
- [x] Thêm approved-plan preflight khó→consult, cheap-check resolved→skip, implementation_started→skip.
- [x] Thêm completion-only→skip và same checkpoint follow-up→skip.
- [x] Sửa consultation SKILL/operations/metadata; giữ primary ownership và final-review riêng.
- [x] Chạy trigger fixtures và kiểm tra không còn positive completion trigger.
**Acceptance:** mọi case có route đúng; chưa đổi transport.
**Rollback:** revert commit CP1, giữ progress/receipts.

### Phase 2 / CP2 — Astra selector và escalation schema

**Goal:** Không còn normal tier lựa chọn Terra/Sol.
**Status: COMPLETE** — receipt: `docs/routing-checkpoints/CP2.json`.
- [x] Test resolver new issue→gpt-6-astra/low; reject arbitrary model/effort và preset bypass.
- [x] Test transitions low→medium→high→extra_high, stop khi sufficient, không skip level/quay lại.
- [x] Test extra_high→stop, invalid schema→stop, missing facts→không auto escalate.
- [x] Implement fixed policy/resolver và minimal schema addition.
- [x] Cập nhật role pins/config catalog liên quan; caller cũ --tier/--role không được silently chọn model cũ. Trả migration_required hoặc compatibility alias đi qua cùng low-first chain, lựa chọn rõ trong docs/tests.
- [x] Chạy unit tests selector/schema, kiểm tra canonical receipt/envelope consumers.
**Acceptance:** fixed Astra và transitions enforce bằng code; mapping xhigh explicit.
**Rollback:** revert CP2; không cài bản WIP vào live plugin.

### Phase 3 / CP3 — Giữ transport, enforce one-pass

**Goal:** Model/effort thực tế theo selection mới.
**Status: COMPLETE** — receipt: `docs/routing-checkpoints/CP3.json`; POSIX rerun: 20/20 passed.
- [x] Test mock child nhận --model gpt-6-astra và effort đúng từng pass; không parent inheritance.
- [x] Test wrong model, wrong effort, non-read-only, tool use, provenance thiếu vẫn fail closed như hiện tại.
- [x] Thay selection input của run-advisor.sh; giữ elevated launcher, stdin packet, private directory, cleanup và cancellation.
- [x] Bỏ vòng hai attempts schema-correction: một child mỗi effort.
- [x] Runtime inspector vẫn chạy trước response validation, không dùng lời model tự khai.
- [x] Test deferred shell handoff vẫn drain terminal và trả đúng một envelope; giữ usage totals/null semantics.
**Acceptance:** mock malformed output chỉ launch một child; regression isolation/handoff pass.
**Rollback:** revert CP3 tại branch dev; giữ installed version đang hoạt động.

### Phase 4 / CP4 — Chống lặp và resume advisor chain

**Goal:** Session ngắt không làm dùng lại opportunity/effort.
**Status: COMPLETE** — receipt: `docs/routing-checkpoints/CP4.json`; POSIX rerun: 6/6 passed.
- [x] Viết tests reserve low, restart, resume→không reserve low lần nữa.
- [x] Test hai callers cùng checkpoint chỉ một owner launch; một key khác không bypass consumed checkpoint.
- [x] Test crash trước launch/sau launch/sau response trước state commit; uncertain không auto retry.
- [x] Implement advisor_chain.py bằng local state pattern hiện có; không database/network service.
- [x] Test journal disabled/clear không xóa safety budget.
- [x] Test sufficient đóng chain, implementation_started khóa opportunity, Extra High kết thúc.
- [x] Test schema retry và follow-up không thể reset chain bằng API cũ.
**Acceptance:** at most one launch/level qua replay/concurrency fixtures; unknown state fail closed.
**Rollback:** revert code tương thích, giữ state và consumed markers; không xóa budget khi rollback.

### Phase 5 / CP5 — Regression, docs và package

**Goal:** Phần không liên quan vẫn hoạt động.
- **Status: COMPLETE — 2026-09-23.** Bằng chứng chạy lại được ghi bổ sung tại `docs/routing-checkpoints/CP5-reverification.json`; receipt lịch sử `CP5.json` được giữ nguyên.
- **Mốc thời gian và phạm vi receipt:** `CP5-reverification.json` là snapshot CP5 ngày **2026-09-23**; lúc đó live runtime chưa được chứng minh, nên `live_runtime_proven: false` vẫn đúng cho snapshot này. Probe live Astra/Low chạy ngày **2026-09-24** và được ghi trong `docs/routing-checkpoints/CP6-runtime-probe.json` với `live_runtime_proven: true` cho đúng một lượt. CP6 tổng thể vẫn `PARTIAL`; không diễn giải giá trị CP5 như trạng thái hiện tại.
- [x] Xác minh installer/role inventory và audit tương thích; không đổi role config của người dùng.
- [x] Giữ modified user roles nguyên trạng; không retire hay xóa file nào trong CP5.
- [x] Đồng bộ SPEC/INVARIANTS/README về fixed Astra, one-pass, checkpoint gate.
- [x] Chạy canonical `verify.sh --static`, full sequential Advisor unit suite, candidate package suite và desktop/mobile Playwright.
- [x] So package/change inventory với baseline; xác nhận thay đổi nằm trong scope policy/state/docs/tests, giữ nguyên auth và static visual assets.
- [x] Xác minh test cũ được cập nhật theo policy mới mà không bỏ security assertions.
**Verification evidence:** static gate PASS (exit 0; embedded Advisor 82/82, candidate 30/30); sequential Advisor suite 82/82; candidate suite 30/30; Playwright 52/52 trên desktop và mobile; `git diff --check` exit 0. Playwright phải ghi artifacts vào thư mục Temp để tránh sandbox `EPERM`; lần chạy thành công đã thực thi đủ tests. Hai typo tài liệu trong consultation skill cũng được sửa (`checkpoint ledger`, `advisor-sol, or`).
**Acceptance:** static/unit suite đạt, không regression unrelated behavior.
**Rollback:** revert đúng commits dependent, không reset broad working tree.

### Phase 6 / CP6 — Live verification và final review

**Goal:** Chứng minh Astra Low chạy thật qua plugin cũ đã sửa.
- **Status: COMPLETE — 2026-09-26.** Evidence tổng hợp: `docs/routing-checkpoints/CP6-completion.json`; probe gốc vẫn được giữ nguyên tại `docs/routing-checkpoints/CP6-runtime-probe.json`.
- [x] Sao lưu cache installed 1.4.5, cài lại từ marketplace local; tại thời điểm probe 42/42 file khớp source. Sau đó chỉ cập nhật wording trong `operations.md`; cache hiện lệch đúng file tài liệu này, 41/42 file vẫn khớp. Không cài lại cache nếu chưa có yêu cầu thay active plugin. User screenshots corroborate marketplace registration và active-plugin response.
- [x] Một bounded Low consultation: runtime inspector xác nhận Astra/low, read-only, managed, zero-tool, schema hợp lệ, usage có ghi nhận; đúng một model attempt.
- [x] Xác minh thứ tự Medium → High → Extra High bằng deterministic fixtures và CP4/CP5 synthetic live-runtime qualification trên Desktop/CLI; ba cạnh escalation liền kề được xác nhận qua wrapper, validator, inspector và ledger. Giữ nhãn synthetic: đây là kiểm tra routing/orchestration, không phải bằng chứng issue thực cần tăng effort. Chi tiết: `docs/advisor-runtime-escalation-verification-plan.md` và `docs/routing-checkpoints/CP4-runtime-evidence-2026-09-27.json`.
- [x] Test skip routine/cheap work, resume/replay không phát sinh lần launch lại; full suite 83/83 PASS.
- [x] Một final review read-only bằng GPT-6 Sol/Medium/fresh context: không có BLOCKER/MAJOR. Hai ghi chú MINOR về digest và WSL ledger path đã được xử lý; primary rerun static gate, không lặp reviewer sau remediation.
- [x] Ghi HEAD `f5c76f383ec949b349baf1a978c4a2bbaf1a6bd7`, candidate digest, test results và giới hạn evidence trong receipt. Runtime qualification tổng hợp đã chạy đủ ladder trên Desktop/CLI; issue thực dừng ở Low. Không claim issue thực tự cần full escalation hoặc token savings.
- [x] Bàn giao backup/restore path và WSL safety-ledger path; không push/publish.
**Acceptance:** exact runtime Low verified; các effort khác có mức evidence rõ; material findings được xử lý đúng policy.
**Verification summary:** canonical static gate PASS (83 Advisor + 30 candidate); fresh full Advisor suite 83/83; candidate suite 30/30; `git diff --check` PASS. Digest tại live probe cho cache/source là `652bcc5308f81276b62411ca593794f711b0244b5a14cbb558c4d8a9a3b8a664`; source hiện tại sau bổ sung operations guidance là `c34440c8499482194ee2512c9eccc016923398c139bd1e3dd813b8dc7ded680f`. Khác biệt duy nhất là tài liệu `operations.md`, không phải runtime code.
**Rollback:** bản cache trước cài đặt còn tại `C:/Users/lehuu/AppData/Local/Temp/advisor-1.4.5-pre-fix-0ba17f59c82148378d5350161afa3ebf` (42 file; digest `b8fb40a451860c2224d12cef6feaaacd64290f6565563baa8b50c4f27089b835`). Restore bằng workflow installer hiện có nếu Quang yêu cầu; không thay cache tự động. Giữ nguyên safety ledger ở `/home/lehuuquang/.codex-advisor/chains` (Ubuntu WSL; mode 700, lock 600); không xóa hay cấp lại budget khi rollback.

### Post-plan safety hardening — 2026-09-27

Phạm vi này xử lý hai rủi ro được phát hiện khi rà code trước khi nhập nhánh; không mở lại CP0–CP6 và không thay đổi kết luận runtime/evidence ở trên.

- [x] Cô lập môi trường subprocess của unit tests khỏi Codex bridge/transport của máy chạy test: private `HOME`, xóa `WSL_DISTRO_NAME`, xóa override `ADVISOR_CODEX_BIN` và trỏ `ADVISOR_TRANSPORT_CONFIG` tới config tạm không tồn tại. Test cần WSL bridge phải bật nó tường minh bằng fixture riêng.
- [x] Cài cleanup/signal traps trước khi tạo private transport run directory để cancellation ở cửa sổ khởi tạo không để sót thư mục tạm.
- [x] Timeout từ process supervisor được phân loại `timed_out` trong envelope và `uncertain/timed_out` trong chain ledger; child exit `124` được giữ là launch failure, không nhầm với deadline của supervisor.
- [x] Fixture interface có evidence settled chuyển sang `skip`; static verifier ghim invariant này và inventory fixture được đồng bộ thành 5/5/4 (consult/skip/boundary).
- [x] Regression evidence: test cleanup từng fail trước thay đổi; test deadline đỏ trước fix vì trả `failed`, rồi pass sau fix. Test child exit `124` cùng test timeout pass 2/2. Test default launch với WSL environment đang hoạt động nhưng không được gọi host bridge pass 1/1.
- [x] Canonical static gate trên Ubuntu WSL pass (exit 0): Advisor unit suite 97/97, candidate package 30/30, shell syntax và static contract đều pass. Lệnh: `wsl.exe --distribution Ubuntu --exec env -u WSL_DISTRO_NAME sh /mnt/d/Program/Codex-Advisor/plugins/advisor/scripts/verify.sh --static`.
- [x] Không chạy lại Playwright trong lần hardening này: thay đổi chỉ ở shell launcher và Python test harness; kết quả CP5 trước đó vẫn là bằng chứng riêng cho web tests, không được gộp vào kết quả gate hiện tại.

**Acceptance:** test subprocess không thể vô tình gọi Codex thật do host environment bị kế thừa; mọi transport run directory đã tạo đều được dọn khi exit/cancel; canonical static gate pass. **Rollback:** revert riêng các thay đổi harness isolation và trap-ordering nếu cần, sau khi lưu evidence; không xóa safety ledger hoặc thay đổi ngân sách chain.

## 8. Checkpoint và resume implementation

Progress ghi phase, current_step, next_action, owned_paths, advisor opportunity đã dùng và evidence.
Mỗi CP hoàn tất theo thứ tự:
1. Relevant checks pass.
2. Commit code/docs owned của phase.
3. Ghi receipt riêng dưới docs/routing-checkpoints/CPn.json: code_commit SHA thật, parent receipt hash, tests/exit codes, changed-files digest và COMPLETE.
4. Commit receipt riêng. Không tự nhúng SHA của một commit vào nội dung chính commit đó.

Resume:
- Đọc plan revision 7, progress và receipts; kiểm tra git status, HEAD, log và code_commit thật.
- Chỉ chọn last-good có COMPLETE và hashes/checks hợp lệ.
- Phase đang dở: đọc diff/untracked files, tiếp tục current_step; không chạy lại CP0.
- Crash sau code commit trước receipt: kiểm tra code, chạy checks còn thiếu và tạo receipt; không làm lại implementation.
- Chỉ chạy lại check cũ khi code/input/environment thay đổi hoặc evidence chưa đủ.
- Không mở advisor opportunity mới chỉ vì đổi session. Nếu opportunity đã dùng hoặc implementation_started thì primary tiếp tục tự xử lý.
- Runtime consultation uncertain theo mục 6, không restart consultation để “thử lại”.

## 9. Rollback an toàn

- WIP chưa commit: giữ file tại chỗ và inventory; sửa đúng hunk bằng apply_patch sau khi xác nhận ownership.
- Commit đã hoàn tất: git revert đúng SHA theo dependency ngược; không git reset --hard, git clean -fd hoặc recursive delete.
- Không đưa edit của Quang vào rollback.
- Installed plugin: restore đúng backup version/digest bằng workflow hiện có; không thay auth/config toàn cục.
- Routing state: giữ consumed/uncertain markers; rollback code không cấp thêm budget. Với probe CP6 trên Ubuntu WSL, `CODEX_HOME=/mnt/c/Users/lehuu/.codex` được chuyển sang `/home/lehuuquang/.codex-advisor/chains`; giữ ledger riêng này ngoài plugin-cache backup.
- Sau rollback chạy relevant gate và ghi receipt lý do, target, checks, next_action.
- Nếu version cũ không đọc được state mới, vô hiệu hóa consultation trong recovery cho tới khi reconcile; không tự bật model cũ trong session đang migrate.

## 10. Definition of Done

- [x] Active advisor routing là Astra Low → Medium → High → Extra High.
- [x] Trigger theo approved-plan checkpoint và explicit standalone của skill nguồn.
- [x] Bỏ completion consultation, same-effort retry và redundant follow-up.
- [x] Runtime model/effort được inspector kiểm chứng, không chỉ ghi trong prompt.
- [x] Session restart không reset lượt gọi.
- [x] Giữ plugin Codex và các chức năng không liên quan; không cloud/backend/API migration.
- [x] Tests và live evidence được phân biệt, rollback/resume có receipt thật.

**Giới hạn xác minh:** Issue thực được xác minh trên runtime dừng ở Astra/Low với usage 15,906 input và 264 output tokens; chain tổng hợp CP4/CP5 xác minh runtime routing đủ Low → Medium → High → Extra High trên Desktop/CLI, nhưng không chứng minh issue thực cần đi qua các mức cao hơn. Không có baseline để khẳng định tiết kiệm token. Ảnh người dùng cung cấp corroborate marketplace/desktop registration và active-plugin response; runtime proof dựa vào receipt có inspector, schema và usage. Cache hiện chưa nhận wording WSL mới trong `operations.md`; không có thay đổi runtime nào sau probe và không thực hiện reinstall trong phiên này.
