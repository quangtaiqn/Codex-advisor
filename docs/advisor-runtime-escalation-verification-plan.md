# Kế hoạch kiểm chứng runtime chính và escalation tự động

Ngày: 2026-09-26. Trạng thái: đề xuất, chưa triển khai hoặc chạy inference trong lượt lập kế hoạch.

## Mục tiêu và ranh giới bằng chứng

Đưa transport từng chạy qua bridge WSL tạm thành đường chạy được cài đặt, cấu hình và kiểm chứng lâu dài cho cả parent Codex CLI và parent Codex Desktop trên máy Quang. Giữ model gpt-6-astra; mức low → medium → high → extra_high, với runtime extra_high = xhigh.

Không chuyển nhãn receipt cũ thành bằng chứng môi trường chính. Receipt cũ chỉ là baseline; mỗi host phải tạo receipt mới sau khi cài đặt và sau khi mở lại ứng dụng. Desktop parent gọi child codex exec là một kiến trúc hợp lệ cần kiểm chứng, không có nghĩa child là runtime native Desktop.

Source đã đọc: run-advisor.sh, advisor_chain.py, advisor.toml, consultation/SKILL.md và advisor-execution/references/advisor-protocol.md. Wrapper hiện chạy một child mỗi lần. Ledger cho phép mức tiếp theo sau completion và escalation liền kề; primary agent điều phối lần gọi tiếp theo. File CP6-runtime-probe.json là receipt lịch sử, không phải kết quả kiểm chứng hôm nay. Working tree có nhiều WIP; không reset, clean, stash hoặc ghi đè.

## Định nghĩa thành công

1. Hai host gọi cùng bản plugin đã cài, cùng policy digest và transport đã quản lý; không cần tạo bridge hoặc export biến tạm bằng tay trong từng chat.
2. Mỗi child được xác minh model/effort thực tế, thread riêng, read-only, zero tools, provenance hợp lệ, schema và ledger nhất quán.
3. Parent tự gọi mức liền kề khi có escalation hợp lệ; không cần Quang nhắc “chạy medium”. Stop ngay khi đủ, khi lỗi hoặc sau xhigh; tối đa bốn child/issue.
4. Kết quả tách rõ: khả năng chạy từng mức, điều phối escalation có kiểm soát, và escalation do advisor tự đánh giá trong nghiệp vụ.
5. Không tuyên bố full-chain nghiệp vụ đã pass nếu model dừng sớm. Không retry/đổi checkpoint để tìm một kết quả thuận lợi.

## CP0 — Chốt baseline và lập bản đồ môi trường

- Ghi Git HEAD, status và diff baseline; manifest hash source/plugin đã cài/skill active, version CLI và Desktop, distro WSL, shell thực tế của mỗi host.
- Kiểm tra executable thực sự: đường dẫn codex, npm shim, node nếu cần; python3, jq, sh; CODEX_HOME, session roots và ledger roots. Chỉ ghi metadata cho phép, không dump env hoặc auth.
- Xác định đường parent Windows → WSL → child Windows hiện tại; tìm mọi chỗ cần chuyển Windows/POSIX path, stdin/stdout, cwd, timeout và cancellation.
- Đọc receipt gốc của lần bridge thành công nếu còn; lưu hash và phạm vi chứng minh, không tái tạo log đã mất.
- Xác định nguyên nhân E_ACCESSDENIED bằng probe WSL không inference trong đúng quyền host; không coi elevation đã giải quyết nếu chưa có kết quả.

Đầu ra: environment manifest cho CLI/Desktop, danh sách phụ thuộc và quyết định transport. Gate: biết chính xác executable và nơi runtime evidence được ghi/đọc; chưa gate thì không tiêu thụ checkpoint live.

## CP1 — Ổn định transport chính

Ưu tiên thay đổi nhỏ: đóng gói adapter WSL → Windows CLI bền vững nếu CP0 xác nhận đây là đường phù hợp với auth và session hiện tại. Adapter là thành phần được quản lý, có hash/version và cấu hình được cả hai host đọc; không đặt vào thư mục temp hoặc sửa cache thủ công làm phương thức cài chính.

Nếu ranh giới Windows/WSL không bảo đảm cancellation, ACL hoặc session discovery, so sánh phương án WSL native CLI và Windows native launcher trước khi chốt. Không mặc định WSL native kế thừa auth Windows; không mở rộng thành rewrite đa nền tảng khi chưa cần.

Yêu cầu triển khai:

- Cấu hình executable tuyệt đối bền vững; doctor từ cả hai host báo executable thực dùng và version. Không chỉ dựa vào biến môi trường của terminal mà Desktop không kế thừa.
- Preflight có timeout trước reserve; dùng cùng executable khi launch. Phiên bản chạy được chưa chứng minh inference hoặc model access.
- Bảo toàn argv, stdin, Unicode, đường dẫn có khoảng trắng, exit code và JSON stdout; diagnostic đi stderr. Chuyển path theo từng đối số có hợp đồng, không thay chuỗi hàng loạt.
- Chứng minh private home/transport và ledger có quyền riêng tư phù hợp trên filesystem thực tế; không xem chmod trên mount Windows là đủ bằng chứng ACL.
- Dùng cơ chế auth hiện có, không đọc/copy token sang bridge, không thêm provider/auth path.
- Timeout/cancel phải kết thúc cả Windows child qua WSL, không chỉ giết shell Linux; kiểm tra không còn process mồ côi.
- Giữ runtime inspector, zero-tool, read-only và provenance checks. Không nới validator chỉ để receipt qua.
- Cấu hình máy đặt ở nơi được installer quản lý/preserve; update plugin không âm thầm mất đường dẫn executable.

Gate: doctor và probe tiến trình không inference pass trên cả hai host, kể cả sau mở mới terminal/khởi động lại Desktop. Nếu cần người dùng đóng/mở Desktop, dừng đúng phần phụ thuộc đó.

## CP2 — Hợp đồng điều phối tự động

Giữ primary agent là chủ điều phối theo advisor-execution; chưa thêm một vòng loop tự trị trong shell. Kiểm tra skill active và plugin không lệch hướng dẫn.

Luồng bắt buộc:

1. Đọc parent identity và ledger, tạo một issue/checkpoint trước implementation; gọi low qua installed wrapper.
2. Drain đúng process đến exit terminal, trích đúng một envelope; kiểm tra runtime/schema, result digest và state tương ứng.
3. Nếu next_level null: stop. Nếu lỗi/uncertain/schema invalid/runtime mismatch: stop, không corrective retry.
4. Nếu escalation liền kề có reason, unresolved_difficulty và required_resolution: primary xác minh rồi gọi next level với cùng checkpoint và authorization cần thiết. Không coi riêng --chain-authorized là bằng chứng hợp lệ.
5. Chỉ bổ sung context cần thiết; ghi packet digest từng mức và giữ policy identity của chain.
6. Sau extra_high/xhigh luôn stop; báo hạn chế nếu chưa giải quyết được. Implementation lock chặn mở lại chain.

Gate: định nghĩa rõ “tự động” là parent tiếp tục trong lượt thực thi sau khi đã được phép chạy cả chain; quyền hệ thống vẫn được tôn trọng, không hứa loại bỏ mọi approval UI.

## CP3 — Regression và fault injection không dùng model thật

Primary đọc test-audit trước khi viết/sửa test; chọn assertions theo hành vi và chứng minh test bắt được lỗi mục tiêu. Test double chỉ chứng minh cơ chế, không gắn nhãn live.

Ma trận tối thiểu:

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| low đủ | Một launch, stop, không reserve medium |
| Ba escalation hợp lệ | Thứ tự low/medium/high/xhigh, mỗi mức một lần |
| Skip level, thiếu lý do, malformed/duplicate JSON | Reject, không child kế tiếp |
| model/effort/provenance/isolation sai hoặc tool call | Runtime reject |
| executable hỏng/timeout preflight | Không reserve, không inference |
| Lỗi sau reserve | failed hoặc uncertain đúng nguyên nhân, không replay |
| Resume sau completed và escalation hợp lệ | Chỉ next level chưa dùng |
| Resume reservation thiếu terminal evidence | uncertain/block, không launch lại |
| Hai caller cùng checkpoint | Không double launch |
| Implementation đã bắt đầu, policy drift | Chặn theo hợp đồng |
| Cancel/timeout qua WSL | Không child mồ côi, state terminal an toàn |
| Unicode/path có khoảng trắng | stdin/argv/output giữ nguyên |

Chạy targeted tests, Advisor suite, packaging suite và static gate theo entrypoint hiện hành, ghi command/exit code/số test thực tế. Không copy số pass từ báo cáo cũ. Sau non-trivial implementation và initial verification, chạy một final-review read-only theo skill; primary sửa và kiểm chứng finding, không mở review lặp cho cùng fix.

## CP4 — Cài bản candidate và live trên cả hai host

Chốt candidate digest sau sửa và review; backup cấu hình cài đặt sẽ thay, giữ nguyên ledger lịch sử. Cài bằng cơ chế installer/update hiện hành, verify source/cache manifest. Không xoá ledger để chạy lại issue.

### A. Canary từng mức

Kiểm tra đường compatibility canary hiện có trước khi tái sử dụng: cùng installed transport, inspector và model cố định, nhưng canary không phải production checkpoint chain. Sau khi được cho phép dùng quota, chạy từng cặp gpt-6-astra với low, medium, high, xhigh một lần từ mỗi host. Không gọi codex exec trực tiếp để bypass wrapper và không bịa escalation nhằm mở mức cao.

Nếu canary hiện có không đáp ứng hợp đồng, hoàn thiện đường qualification được opt-in rõ ràng, tách khỏi active routing, trước khi dùng. Không lặng lẽ mở direct high trong production.

Gate: tám receipt live (bốn mức × hai host), hoặc báo chính xác ô lỗi/chưa chạy. Đây là bằng chứng khả năng thực thi từng mức, chưa chứng minh escalation.

### B. Escalation nghiệp vụ qua primary thật

Chọn trước một packet về bất định kỹ thuật thực, đầy đủ bằng chứng sẵn có, đáp ứng gate advisor. Không yêu cầu model giả vờ thiếu năng lực, không giấu dữ kiện chỉ để ép lên mức. Mỗi host một chain, tối đa bốn child; primary tự chuyển mức khi advisor thực sự yêu cầu và validator/ledger cho phép.

- Nếu chain đi hết: xác minh ba chuyển mức từ output model thật, log parent thật và ledger.
- Nếu dừng low/medium/high: ghi stop-on-sufficient PASS; các cạnh chưa đi qua ghi NOT_EXERCISED. Không chạy lại cùng issue để săn full chain.
- Nếu model trả escalation nhưng primary không tiếp tục dù điều kiện đủ: đây là lỗi điều phối cần sửa, không phải thiếu model access.

### C. Kiểm chứng toàn bộ đường chuyển mức khi B dừng sớm

Không có cách bảo đảm một advisor trung thực luôn yêu cầu đủ ba escalation. Muốn coverage tái lập, đề xuất một chế độ qualification riêng được duyệt rõ trong policy: kịch bản escalation tổng hợp có kiểm soát, runtime child thật, dùng cùng bộ điều phối/validator/ledger, state namespace riêng và nhãn synthetic_scenario=true.

Không sửa output sau runtime validation, không viết tay ledger, không nới stop-on-sufficient cho nghiệp vụ. Thiết kế chi tiết phải chứng minh fixture không rò vào production và tắt mặc định. Nếu protocol active chưa cho phép chế độ này thì không chạy; dùng kết quả CP3 cùng A/B và giữ full-chain live là PARTIAL.

Receipt của C chỉ chứng minh điều phối tự động trên kịch bản kiểm thử với runtime thật. Không chứng minh advisor tự thấy cần escalation trong công việc thực. Nếu chỉ viết một harness mới tự gọi bốn mức mà không đi qua bộ điều phối production, không được tính là pass điều phối production.

Ngân sách đề xuất cho đợt đầu: A tối đa 8 child; B tối đa 8 child; C tùy chọn tối đa 8 child nếu được duyệt. Tổng trần 24, không bắt buộc dùng hết. Deadline mỗi call theo cấu hình, thêm giới hạn thời gian tổng đợt trước khi chạy. Không retry cùng mức/issue; lỗi kết thúc case, sửa lỗi phải lập đợt verification mới có thay đổi và lý do rõ, không tự reset ngân sách.

## CP5 — Persistence, resume và bàn giao

- Mở terminal mới, khởi động lại Desktop, xác minh plugin/skill/executable đúng manifest; không export lại biến tạm.
- Mỗi host một smoke low mới tối đa một child, mục tiêu kiểm chứng cold start rõ ràng; cộng thêm tối đa hai child vào ngân sách nếu duyệt (trần toàn đợt 26).
- Dùng fault injection ở CP3 để chứng minh no-replay. Live resume chỉ chạy khi có chain thật đang ở completed với next action liền kề; không làm giả reservation hoặc cố tình phá một chain nghiệp vụ để lấy log.
- Kiểm tra upgrade giữ cấu hình máy và ledger; rollback khôi phục package/config backup nếu candidate lỗi, không khôi phục ledger cũ để tái tiêu thụ mức đã dùng.
- Giao hướng dẫn cài, doctor, troubleshooting, rollback; ghi rõ phạm vi Windows/WSL và hai host đã kiểm chứng, không suy rộng macOS/Linux khác.

## Hợp đồng evidence và báo cáo

Mỗi receipt ghi: thời gian/run ID, host parent CLI/Desktop và version, source/plugin/adapter/policy digest, executable/version, shell/distro, checkpoint/case kind, parent/child identity, requested/observed model-effort, isolation, provenance, tool count, result digest, escalation, ledger trước/sau, exit code, elapsed time và usage availability. Không suy effort từ số reasoning tokens.

Giữ envelope đã xác minh cùng tham chiếu/hash rollout bền vững; kiểm tra đường evidence còn tồn tại sau cleanup. Không vô hiệu trap cleanup để giữ packet/event tạm. Nếu cần evidence export, xuất allowlist metadata trước cleanup, bảo vệ quyền và không chứa auth/full prompt. Bản báo cáo chia sẻ phải redact định danh riêng tư; bản local giữ liên kết để kiểm toán.

| Hạng mục | CLI | Desktop |
| --- | --- | --- |
| Transport chính + cold start | PASS: phiên CLI mới nạp Advisor 1.4.5; bridge và low smoke được kiểm chứng | PASS: Desktop restart; parent được phục hồi, bridge và low smoke được kiểm chứng |
| Runtime low/medium/high/xhigh | PASS: A canary 4/4; C qualification chạy thật cả bốn mức | PASS: A canary 3/4; B low riêng biệt xác nhận mức còn thiếu; C qualification chạy thật cả bốn mức |
| Escalation nghiệp vụ quan sát được — B | PASS: issue thực dừng ở low theo stop-on-sufficient; mức cao hơn không được yêu cầu | PASS: issue thực dừng ở low theo stop-on-sufficient; mức cao hơn không được yêu cầu |
| Full-chain qualification C | PASS: 4/4 child, đủ ba cạnh adjacent qua protocol/validator/ledger đang hoạt động | PASS: 4/4 child, đủ ba cạnh adjacent qua protocol/validator/ledger đang hoạt động |
| Stop/no-replay/cold-start | PASS: ledger kết thúc stop; CP5 smoke một child sau cold start | PASS: ledger kết thúc stop; restart Desktop và CP5 smoke một child |

Trạng thái dùng: PASS, FAIL, BLOCKED, NOT_RUN, NOT_EXERCISED. Overall PARTIAL nếu chưa có đủ bằng chứng mục tiêu; không dùng test pass thay runtime pass. Repo có thể pass gate trong khi host rollout vẫn BLOCKED.

Qualification C dùng tình huống tổng hợp được bật tường minh và có namespace riêng. Kết quả C chứng minh orchestration đã chạy các chuyển mức liên tiếp qua child runtime thật; nó không chứng minh một vấn đề kỹ thuật thực tế cần tăng effort. Hai chain B vẫn là bằng chứng riêng cho stop-on-sufficient.

## Phạm vi lượt lập kế hoạch ban đầu

Khi tạo tài liệu, chỉ thêm plan; chưa sửa plugin, cài adapter, cập nhật cache, chạy model, commit hoặc push. Phần dưới ghi nhận lượt thực thi sau đó.

## Nhật ký thực thi — 2026-09-27 (Asia/Saigon)

- **CP0 / WSL:** host `wsl --status` và `wsl -l -v` pass; không sửa hoặc cài lại WSL. Codex CLI `0.155.0`, Windows Node `22.22.1`, distro Ubuntu.
- **CP1 / bridge:** installer cài bridge riêng tư tại `~/.codex-advisor/transport`; Codex preflight pass, doctor `status=ok`, executable source `installed-wsl-bridge`, session path trỏ tới Windows Codex sessions. Bridge SHA-256: `35057bb567c0bfc46c39f686532347a0538496fc7d1c2bbca006dd91e9c7862a`. Windows Node đọc/ghi file qua WSL UNC với dấu cách/Unicode pass. Probe hủy tiến trình thật kết thúc cả Windows Node cha và con; không cần emergency cleanup.
- **Giới hạn CLI:** `codex exec --help` xác nhận `--ignore-user-config` và `--ignore-rules` vẫn được hỗ trợ. `codex app-server --help` không công bố hai cờ này; doctor vì thế báo `discovery_protocol=unsupported` và Discovery tiếp tục fail closed. Đây là giới hạn catalog discovery, không được tính là bridge/runtime pass.
- **CP2–CP3:** hợp đồng điều phối và test/fault gates pass. Lệnh `env -u WSL_DISTRO_NAME sh plugins/advisor/scripts/verify.sh --static` kết thúc mã 0: **94/94 Advisor tests**, **30/30 packaging tests**, static gate PASS; `git diff --check` PASS. Verifier và test runner cô lập synthetic Codex khỏi bridge cài đặt; WSL-specific tests dùng config riêng.
- **Candidate install:** `codex plugin add advisor@advisor --json` thành công, version `1.4.5`. Cache có 45 file; source/cache inventory giống hệt, tree SHA-256 `D706EC21D11E110B79BDDE5A31671A3AF39C00D16893E3B93FED05F6D8F35FFB`.
- **Sự cố gate trước khi cô lập:** một lần verifier và Python suite chạy khi `WSL_DISTRO_NAME` còn bật đã chọn bridge production thay fake `PATH`. Metadata session ghi nhận 22 `codex exec` session trong cửa sổ đó: 17 `gpt-6-astra/low`, 4 `manual/model/high`, 1 `future/model/max`. Đây là session/turn-context metadata, **không phải receipt canary hoặc bằng chứng chain**; có thể đã phát sinh usage. Không tái chạy để xác nhận. Test ledger dùng `CODEX_HOME` tạm; không dùng ledger production. Sau đó không còn Windows Node test process.
- **CP4 / CP5 — snapshot trước khi duyệt quota:** chưa chạy canary A, chain B, qualification C, cold-start smoke hay restart Desktop; các session ngoài ý muốn ở trên bị loại khỏi toàn bộ bằng chứng. Desktop cold start vẫn cần kiểm tra riêng.

## Nhật ký tiếp nối — 2026-09-27 (Asia/Saigon)

- **Quota được duyệt:** A tối đa 8 + B tối đa 8, tổng cứng 16 child; không bắt buộc dùng hết. Nếu B dừng sớm thì kiểm tra C; không chạy CP5. Kết quả thực tế: A dùng 7 child, B dùng 2 child, tổng 9/16. Các preflight lỗi không launch child không tính quota. Không replay child.
- **A — canary runtime:** CLI PASS 4/4 (`gpt-6-astra`, low/medium/high/xhigh). Desktop PASS 3/4; low dừng trước launch vì private Codex home thiếu, không có child và không chứng minh model incompatibility. Bên cạnh đó, B Desktop low đã chạy thật thành công, nhưng được giữ riêng khỏi ma trận canary A. Mỗi compatibility receipt chỉ lưu pair/version/contract/revision/selected; không có lineage host/run đầy đủ.
- **B — Desktop:** parent `01a0de62-021a-7431-8bbc-13d5b6de30a2`, child `01a0df14-fa7e-7813-a8fd-beb81e0bffde`; installed Advisor `1.4.5`, CLI `0.155.0`, installed WSL bridge. Wrapper và persisted-runtime inspector exit 0; model/effort `gpt-6-astra/low`, transport `codex-exec`, sandbox `read-only`, permission `managed`. Envelope `completed/accepted`, `next_level=null`; ledger `complete`, low `completed`, `next_action=stop`. Không chạy mức cao hơn.
- **B — CLI:** parent `01a0df18-28a8-7a72-8d1e-269fbae29f96`, child `01a0df20-3ad4-7902-a8b3-0c8e2e5507a0`; cùng installed plugin/bridge/version. Parent inspector, wrapper, child inspector và ledger đều exit 0; runtime `gpt-6-astra/low`, `codex-exec`, `read-only`, `managed`. Envelope `completed/accepted`, `next_level=null`; ledger `complete`, low `completed`, `next_action=stop`. Không chạy mức cao hơn.
- **Lỗi preflight đã phân loại:** hai lần inspector ban đầu trả `unavailable` vì caller bỏ cờ bắt buộc `--sessions-dir`; chưa có child nào chạy. Với cú pháp đúng, cả parent Desktop và CLI trả `available`. WSL `E_ACCESSDENIED` chỉ xuất hiện trong sandbox; cùng inspector chạy elevated pass. Không sửa hoặc cài lại WSL. Một lần khởi chạy CLI parent cũng bị sandbox chặn ghi `state_5.sqlite`; chạy elevated tạo parent thành công.
- **C — trạng thái tại snapshot trước khi triển khai mode:** điều kiện chuyển sang C đã xảy ra vì hai chain B đều dừng ở low. Tuy nhiên `plugins/advisor/scripts`, active consultation skill và tests không có `synthetic_scenario` hoặc qualification mode; active protocol chỉ chấp nhận escalation do envelope thật yêu cầu. Theo CP4-C, không chạy khi protocol chưa cho phép mode riêng; C ghi `BLOCKED / NOT_RUN`, không launch child tổng hợp. Các cạnh low→medium→high→xhigh vẫn `NOT_EXERCISED`; không tuyên bố escalation tự động end-to-end đã được chứng minh.
- **Evidence:** manifest không chứa prompt/response tại [`CP4-runtime-evidence-2026-09-27.json`](routing-checkpoints/CP4-runtime-evidence-2026-09-27.json), SHA-256 `5C0FBEB025E562CFFE1C62C653F9382B4356B16E3E54B86EC6FBE15AEB906106`. Manifest giữ lineage B và nêu rõ các canary A chưa có child identity trong compatibility receipt. Catalog pair-only không được dùng làm bằng chứng host coverage.
- **CP5:** cold-start smoke và restart Desktop `NOT_RUN`, theo yêu cầu.

Tổng trạng thái tại snapshot này là **PARTIAL**: installed transport và các mức model có live runtime evidence, nhưng hai chain nghiệp vụ đều dừng đúng ở low; C chưa thể chạy theo active protocol. Trạng thái cuối được ghi ở nhật ký tiếp nối bên dưới. Không commit hoặc push.

## Nhật ký tiếp nối — CP4-C và CP5 (2026-09-27, Asia/Saigon)

- **C được duyệt và triển khai:** thêm ADVISOR_ENABLE_SYNTHETIC_QUALIFICATION=1, scenario full-adjacent-escalation-v1, và namespace theo run UUID vào active wrapper. Mode mặc định tắt; yêu cầu route/level/checkpoint rõ ràng; cùng wrapper, validator, inspector và ledger production được dùng. Mỗi envelope được xác thực trước khi tiếp tục; receipt/response không bị sửa tay. Thay đổi nằm trong plugins/advisor/scripts/run-advisor.sh, consultation skill/operations, tests và static verifier.
- **Kiểm chứng mã:** Advisor suite 96/96, packaging suite 30/30, static gate và shell syntax PASS; git diff --check PASS. Final review độc lập PASS, không có blocker/major. Plugin cache advisor@advisor 1.4.5 được refresh; 45 file source/cache khớp. Tree SHA-256 hiện tại 7016ebc61abe1b4295083936f33ef649840e2611bfd59549bcf0c88ca4b40de1; run-advisor.sh SHA-256 D5FE86F37D7B30BE802EB9B84A6389E411E72FFB926FB4AF6B75C8934532D37E.
- **C — Desktop:** parent 01a0de62-021a-7431-8bbc-13d5b6de30a2; bốn child Astra chạy low → medium → high → extra_high/xhigh. Cả bốn wrapper và runtime inspector exit 0; mỗi envelope completed/accepted, mang nhãn synthetic đúng run; ledger theo từng bước yêu cầu đúng reserve cho mức kế tiếp và kết thúc complete/stop. Không có retry child.
- **C — CLI:** parent mới 01a0df60-a764-7af1-b7cc-5d0ab15ae7f7; bốn child theo cùng chuỗi effort. Cả bốn wrapper và runtime inspector exit 0; envelope/ledger xác nhận đủ ba cạnh adjacent; chain kết thúc complete/stop. Không có retry child.
- **Giới hạn diễn giải:** C sử dụng output escalation tổng hợp do mode qualification tạo trong prompt trước khi reservation; child runtime và response vẫn thật, validator/ledger xử lý output thật. Đây là bằng chứng cho khả năng orchestration tự đi tiếp khi envelope yêu cầu nấc liền kề, không phải bằng chứng cho quyết định tăng effort trên issue thực. Trong B, issue thực vẫn dừng đúng ở low.
- **CP5 — CLI cold start:** phiên mới 01a0df66-50f9-71b3-8a51-c071a56d678e báo codex-cli 0.155.0; codex plugin list --json xác nhận Advisor 1.4.5 installed=true, enabled=true; parent inspector available. Một child low thường, không synthetic, trả completed/accepted, next_level=null; inspector pass, ledger complete/stop.
- **CP5 — Desktop cold start:** tiến trình Desktop cũ PID 16936 được restart; executable cùng đường dẫn chạy lại với PID 27448. Parent inspector xác nhận phiên được phục hồi available. Một child low thường, không synthetic, trả completed/accepted, next_level=null; inspector pass, ledger complete/stop.
- **Evidence manifest cập nhật:** docs/routing-checkpoints/CP4-runtime-evidence-2026-09-27.json, SHA-256 E5B8311623A5BE53AB5C36AB903EB67F32A7656365F0B0C7C41C988F85D237C6. Manifest giữ lineage, packet/result digests, inspector và ledger metadata; không chứa prompt, response hoặc raw rollout.
- **Ngân sách:** A 7 + B 2 + C 8 + CP5 2 = **19/26 child**; C dùng 8/8, CP5 dùng 2/2. Không chạy lại A/B, không retry child, không commit/push. WSL không bị sửa hoặc cài lại; các thao tác phụ thuộc WSL chạy ngoài sandbox theo approval.

Tổng trạng thái CP4/CP5 là **PASS** cho tiêu chí qualification escalation và cold start trên cả hai host. Bằng chứng C mang tính synthetic như đã nêu; trạng thái này không khẳng định một issue thực cần escalation.
