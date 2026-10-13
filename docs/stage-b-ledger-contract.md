# Contract ledger giai đoạn B

Baseline A: ca963d330db8207bded885659e2f9376224f8678. Contract này định nghĩa implementation B, không phải live qualification.

## Identity và quyền

Primary chọn namespace qua `--ledger-dir`, provision riêng bằng `advisor_ledger.py init`; launcher không tự init, repair hoặc reset. Namespace do owner tin cậy quản lý. `--project-root` phải là Git checkout; identity là SHA256 đường dẫn Git common directory thực (ổn định giữa worktrees). Không dùng remote mutable hoặc session làm quota key. Registry bind issue ID, canonical packet, policy revision và parent; alias/tier không nằm trong key. Root khác được primary provision là namespace khác, không hứa chống trusted owner tạo namespace mới/xóa toàn bộ marker/state/key hoặc rollback filesystem. Không có external monotonic authority.

Canonical packet: UTF-8 strict, Unicode NFC, CRLF→LF, mỗi dòng collapse whitespace và trim, bỏ dòng rỗng; ISO date/datetime tokens chuẩn hóa thành `<timestamp>` để chỉ đổi timestamp không cấp quota. SHA256 canonical text giữ thứ tự, phần nội dung khác, case và dấu câu. Filename không là identity. Registry dedupe canonical digest trong cùng project/namespace bất kể ID/parent/alias. Không hứa nhận diện paraphrase hoặc mọi cách ghi thời gian. Packet raw SHA256 vẫn bind runtime receipt như A; packet headings vẫn theo format launcher hiện hành. Cùng issue ID không được đổi packet/policy. Material revision dùng ID mới, packet khác, `--supersedes`, reason nonblank và evidence SHA256 mới; primary chịu trách nhiệm tính material của evidence, backend kiểm tra liên kết/shape/khác biệt.

Parent/source là execution provenance. Transfer chỉ từ accepted inactive chain, với authentic receipt và persisted runtime của parent cũ, parent mới được inspector xác minh; transaction ghi transfer proof và parent mới. Không bỏ guard parent của receipt/runtime cũ. Transfer không đổi issue/levels/packet/policy hoặc cấp low. Active/unknown execution không transfer khi thiếu proof.

## State machine

Windows drive-mapped Git common paths (`/mnt/<drive>/...`) được case-fold trước hash: đổi hoa/thường của cùng repo không tạo project/quota mới. Paths Linux thường giữ case. Đây là canonicalization bảo thủ cho drive mounts; nếu thư mục Windows bật case-sensitive và có hai repo chỉ khác case, chúng chia sẻ identity/quota thay vì cấp duplicate. Clone/move sang Git common directory khác là project khác; không cam kết chống owner thay topology hoặc alias mount độc lập.

| Transition | Quy tắc |
| --- | --- |
| unseen → reserved | Preflight executable, parent, packet, schema và previous-result đạt; lock toàn namespace; kiểm tra canonical index/issue/quota và reserve atomically. Durable reservation là điểm tuyến tính hóa consumed quota. |
| reserved → started | Cùng launcher PID/start/boot identity ghi marker durable trước gọi supervisor/spawn. Chỉ một transition; crash quanh syscall đều mất lượt. |
| started → accepted | Runtime inspector + local response validator + HMAC receipt đạt; bind execution/issue/namespace/project/packet/policy, lưu receipt digest/next_level và commit durable trước stdout. |
| reserved/started → failed/cancelled/timed_out/unknown | Không release quota. Nếu persist lỗi, reservation còn giữ; không trả accepted hoặc tự retry. |
| accepted → next reserved | Previous sealed B receipt đúng persisted digest/execution; next_level adjacent, primary flag và admission A đạt; consume receipt và reserve cùng transaction. |
| accepted sufficient/extra_high → closed | next_level null hoặc terminal đóng issue vĩnh viễn. Prune không mở lại. |

At-most-once là không spawn lại level, không bảo đảm completion. Một command chạy một level, không auto-loop. Mọi lỗi trước reserve có attempts=[]; lỗi sau reserve không trả quota. Process evidence PID + `/proc` starttime + boot ID; PID đơn lẻ không là ownership proof. Cleanup vẫn do lifecycle A, reconcile không kill process.

## Storage và durability

Owner module storage giữ một JSON registry version 1 và một lock inode cố định, không nhiều databases. Directory 0700, files 0600, UID hiện tại, no-follow từng thành phần, regular files nlink=1, bounded đọc và checksum/schema validation. Linux filesystem bắt buộc; DrvFS/Windows paths từ chối. Không có ephemeral/test-only mode; mọi namespace, kể cả fixture, dùng persistent Linux filesystem. Tmpfs/DrvFS bị từ chối. Init độc lập ghi epoch marker, fsync file và directory; mất registry hoặc marker sau init fail closed, không tự init lại.

Transaction: bounded exclusive flock trên stable lock; đọc/validate version, epoch và checksum; write unique O_EXCL/no-follow temp file; complete-write loop, fsync file, atomic replace qua directory fd, fsync directory rồi mới return. Rename một mình không đủ. Read/status cũng lock và validate, không mutate. Owner có thể sửa toàn bộ state/code/key nằm ngoài threat model; checksum phát hiện corruption, không thay authentication.

Giới hạn 1024 issues và 8 MiB registry; đầy thì fail closed. Prune chỉ chi tiết receipt/runtime của closed issues, giữ canonical index, issue IDs, policy, execution IDs, levels và digest tombstones vĩnh viễn. Journal usage độc lập, không cấp launch. Không lưu plaintext packet hoặc session trong registry; chỉ digests, IDs, timestamps và bounded provenance.

## Compatibility, migration và recovery

B output envelope 4 / transport 1.6; A envelope3/transport1.5 vẫn đọc cho accounting lịch sử nhưng không authorize B escalation. Không phục hồi advisor_policy.py hoặc --chain-authorized. Authenticated B receipt bao ledger binding; backend đối chiếu digest persisted, không tin accepted/consumed caller fields.

Legacy registry không tự migrate: status/init báo version/unsafe state, giữ nguyên để primary backup/quarantine và xem xét migration riêng. Chain A đang dở phải được khai báo/import thành closed tombstone bằng authentic A receipt và original packet; không silent restart low. Import lỗi giữ original bytes/state. Không dùng A receipt làm previous-result B. Owner có trách nhiệm đưa known legacy activity vào namespace trước B launch; không có cơ chế suy ra toàn bộ A history từ journal.

`status` đọc state. `reconcile` kiểm tra execution/launcher identity; nếu launcher còn sống thì từ chối. Với authentic sealed B receipt và persisted runtime đủ proof, finalize cùng execution; thiếu proof chuyển unknown, không spawn replacement. Receipt bị mất hoặc runtime không còn đủ bằng chứng nghĩa là safe stop, không cấp lại lượt. `transfer` yêu cầu proof của old/new parent, không chuyển unknown chain. Không có reset/release-quota CLI.

## Ownership và kiểm chứng

Storage: advisor_ledger_store.py. Identity/state machine/CLI: advisor_ledger.py. Parent/runtime/response/HMAC: admission/acceptance A. Spawn/output/usage/cleanup: run-advisor.sh. Tests mới qua production launcher, fake provider ở boundary, concurrency có barrier, crash/storage fault injection chỉ trong test process qua patch OS API hoặc actual killed launcher; không thêm production test-only flags.

Safety A giữ: aliases standard/specialist/Terra/Sol/Astra low-first, gpt-6-astra, low→medium→high→extra_high (xhigh), primary confirmation, stop sufficient, no retry/fallback, zero-tool, read-only, runtime provenance và bounds.

## Parent inspector streaming (R3)

`advisor_parent.py` validates strict UTF-8 JSONL through EOF before returning available, retaining only parent metadata. Admission retains its 3-second probe; doctor retains 2 seconds. The parser checks its 2.5-second deadline between bounded reads and directory entries; callers retain their outer deadlines. Bounds: 64 MiB per rollout, 1 MiB per line, 100000 records and 100000 directory entries. Oversized workloads fail closed; timing is workload/host-specific.

Unique parent ID, complete-history sandbox consistency (read-only/workspace-write) and one nonempty permission type retain the existing predicates. Duplicate-key/nonfinite JSON, invalid UTF-8, non-object records and non-newline-terminated tails are deliberately rejected as additional hardening; the old jq reader did not guarantee these checks. No successful early return after first safe metadata.

Sessions/rollout opens do not follow links; file UID, regular type and nlink1 are checked. Descriptor-anchored directory streaming checks each entry before accumulation and rejects any traversal/classification IO error. Directory-relative descriptors, before/after inode/size/mtime/ctime checks and uniqueness rescan reject observed append/replacement races. Windows session POSIX mode600 is not required; ledger storage remains Linux-private. Owner-controlled edits after inspection remain outside the existing trust boundary. A faster inspector must still reject the current mixed/unsafe parent; it does not prove live model/provider availability.
