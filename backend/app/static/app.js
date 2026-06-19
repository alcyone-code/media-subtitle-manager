// Media Subtitles Manager Client Logic

// 애플리케이션 상태 관리
const state = {
    currentPath: '/media',
    parentPath: '',
    selectedPath: null,
    previewGroups: [], // 폴더 단위 매칭 미리보기 데이터
    eventSource: null
};

// DOM 요소 참조
const elements = {
    btnNavUp: document.getElementById('btn-nav-up'),
    txtCurrentPath: document.getElementById('txt-current-path'),
    folderList: document.getElementById('folder-list'),
    btnSelectTarget: document.getElementById('btn-select-target'),
    txtSelectedPath: document.getElementById('txt-selected-path'),
    
    // Tabs
    tabMatch: document.getElementById('tab-match'),
    tabConvert: document.getElementById('tab-convert'),
    contentMatch: document.getElementById('content-match'),
    contentConvert: document.getElementById('content-convert'),
    
    // Actions
    btnMatchPreview: document.getElementById('btn-match-preview'),
    btnConvertRun: document.getElementById('btn-convert-run'),
    chkRemoveSmi: document.getElementById('chk-remove-smi'),
    selSrtExt: document.getElementById('sel-srt-ext'),
    
    // Preview
    previewSection: document.getElementById('preview-section'),
    txtPreviewCount: document.getElementById('txt-preview-count'),
    previewList: document.getElementById('preview-list'),
    btnExecuteSync: document.getElementById('btn-execute-sync'),
    
    // Terminal
    terminalConsole: document.getElementById('terminal-console'),
    btnClearLog: document.getElementById('btn-clear-log'),
    
    // Version
    appVersion: document.getElementById('app-version')
};

// 초기화
document.addEventListener('DOMContentLoaded', () => {
    initFolderBrowser();
    initTabs();
    initActionEvents();
    initSSE();
    loadAppVersion();
});

// 1. 실시간 로그 수신을 위한 SSE 설정
function initSSE() {
    if (state.eventSource) {
        state.eventSource.close();
    }
    
    state.eventSource = new EventSource('/api/logs/stream');
    
    state.eventSource.onmessage = (event) => {
        const msg = event.data;
        if (!msg) return;

        console.log("SSE Received:", msg); // 브라우저 디버깅용 로그

        if (msg.includes('[PROGRESS]')) {
            try {
                const idx = msg.indexOf('[PROGRESS]');
                const jsonStr = msg.substring(idx + 10).trim();
                const data = JSON.parse(jsonStr);
                updateProgressUI(data);
            } catch (e) {
                console.error("Failed to parse progress JSON:", e);
                appendLog(msg);
            }
        } else if (msg.includes('[RESULT]')) {
            try {
                const idx = msg.indexOf('[RESULT]');
                const jsonStr = msg.substring(idx + 8).trim();
                const data = JSON.parse(jsonStr);
                showResultUI(data);
            } catch (e) {
                console.error("Failed to parse result JSON:", e);
                appendLog(msg);
            }
        } else {
            appendLog(msg);
        }
    };
    
    state.eventSource.onerror = (err) => {
        console.error("SSE Connection Error:", err);
        // 재연결 대기 등 처리 가능
    };
}

function appendLog(message) {
    if (!message || message.trim() === '') return;
    
    const logLine = document.createElement('div');
    logLine.classList.add('log-line');
    
    // 로그 성격에 따른 스타일 매핑
    if (message.includes('[ERROR]')) {
        logLine.classList.add('error-msg');
    } else if (message.includes('[INFO]')) {
        // 기본값 녹색 외에 인포 텍스트 스타일
    } else {
        logLine.classList.add('system-msg');
    }
    
    logLine.textContent = message;
    elements.terminalConsole.appendChild(logLine);
    
    // 자동 스크롤
    elements.terminalConsole.scrollTop = elements.terminalConsole.scrollHeight;
}

// 2. 폴더 브라우저 초기화 및 통신
function initFolderBrowser() {
    loadDirectory(state.currentPath);
    
    elements.btnNavUp.addEventListener('click', () => {
        if (state.parentPath) {
            loadDirectory(state.parentPath);
        }
    });
    
    elements.btnSelectTarget.addEventListener('click', () => {
        state.selectedPath = state.currentPath;
        elements.txtSelectedPath.textContent = state.selectedPath;
        
        // 제어 버튼들 활성화
        elements.btnMatchPreview.disabled = false;
        elements.btnConvertRun.disabled = false;
        
        appendLog(`[SYSTEM] 작업 대상 폴더로 선택됨: ${state.selectedPath}`);
    });
}

async function loadDirectory(path) {
    elements.folderList.innerHTML = `<li class="loading-item"><i class="fa-solid fa-spinner fa-spin"></i> 디렉토리 로딩 중...</li>`;
    
    try {
        const url = `/api/browse?path=${encodeURIComponent(path)}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`디렉토리를 읽을 수 없습니다: ${response.statusText}`);
        }
        
        const data = await response.json();
        state.currentPath = data.current_path;
        state.parentPath = data.parent_path;
        
        elements.txtCurrentPath.textContent = state.currentPath;
        
        // 상위 폴더 단추 활성화 여부
        elements.btnNavUp.disabled = !state.parentPath;
        
        elements.folderList.innerHTML = '';
        
        // 폴더 목록 구성
        if (data.directories.length === 0) {
            elements.folderList.innerHTML = `<li class="loading-item">하위 폴더가 없습니다.</li>`;
        } else {
            data.directories.forEach(dir => {
                const li = document.createElement('li');
                li.innerHTML = `
                    <div class="folder-item-content">
                        <i class="fa-solid fa-folder"></i>
                        <span>${dir.name}</span>
                    </div>
                    <i class="fa-solid fa-chevron-right" style="font-size: 0.75rem; color: var(--text-muted);"></i>
                `;
                li.addEventListener('click', (e) => {
                    // 현재 폴더 클릭 시 하위 폴더 이동
                    loadDirectory(dir.path);
                });
                elements.folderList.appendChild(li);
            });
        }
    } catch (error) {
        appendLog(`[ERROR] 디렉토리 로드 실패: ${error.message}`);
        elements.folderList.innerHTML = `<li class="loading-item error-msg">디렉토리 정보를 가져오지 못했습니다.</li>`;
    }
}

// 3. 탭 이벤트 초기화
function initTabs() {
    const tabs = [
        { btn: elements.tabMatch, pane: elements.contentMatch, key: 'match' },
        { btn: elements.tabConvert, pane: elements.contentConvert, key: 'convert' }
    ];
    
    tabs.forEach(tab => {
        tab.btn.addEventListener('click', () => {
            tabs.forEach(t => {
                t.btn.classList.remove('active');
                t.pane.classList.remove('active');
            });
            tab.btn.classList.add('active');
            tab.pane.classList.add('active');
            
            // 미리보기 영역 제어: 탭 전환에 따른 숨김 처리 등
            if (tab.key === 'convert') {
                elements.previewSection.classList.add('hidden');
            } else if (tab.key === 'match' && state.previewGroups.length > 0) {
                elements.previewSection.classList.remove('hidden');
            }
        });
    });
}

// 4. 액션 이벤트 핸들러
function initActionEvents() {
    // 로그 지우기
    elements.btnClearLog.addEventListener('click', () => {
        elements.terminalConsole.innerHTML = '';
    });
    
    // 자막 매칭 미리보기 분석 요청
    elements.btnMatchPreview.addEventListener('click', async () => {
        if (!state.selectedPath) return;
        
        elements.btnMatchPreview.disabled = true;
        elements.btnMatchPreview.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 분석 중...`;
        appendLog(`[SYSTEM] 매칭 분석 시작: ${state.selectedPath}`);
        
        try {
            const response = await fetch('/api/match/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ path: state.selectedPath })
            });
            
            if (!response.ok) {
                const errData = await response.json();
                throw new Error(errData.detail || '분석 중 실패');
            }
            
            state.previewGroups = await response.json();
            
            // 매칭된 총 자막 개수 세기
            let totalMatches = 0;
            state.previewGroups.forEach(group => {
                totalMatches += group.matches.filter(m => m.subtitle_path && m.video_path).length;
            });
            
            elements.txtPreviewCount.textContent = `${totalMatches}개 파일 매칭 예정`;
            
            renderPreview();
            
            if (state.previewGroups.length === 0) {
                appendLog(`[SYSTEM] 매칭 가능한 동영상 및 자막 파일 그룹이 존재하지 않습니다.`);
                elements.previewSection.classList.add('hidden');
            } else {
                elements.previewSection.classList.remove('hidden');
                appendLog(`[SYSTEM] 미리보기 분석 완료.`);
            }
            
        } catch (error) {
            appendLog(`[ERROR] 미리보기 분석 중 오류 발생: ${error.message}`);
            elements.previewSection.classList.add('hidden');
        } finally {
            elements.btnMatchPreview.disabled = false;
            elements.btnMatchPreview.innerHTML = `<i class="fa-solid fa-magnifying-glass"></i> 매칭 미리보기 분석`;
        }
    });

    // 자막 매칭 실행 (이름 변경 일괄 적용)
    elements.btnExecuteSync.addEventListener('click', async () => {
        if (state.previewGroups.length === 0) return;
        
        // 실제 변경할 파일(ready 상태이고 제안된 경로가 있는 파일)만 추출
        const targets = [];
        state.previewGroups.forEach(group => {
            group.matches.forEach(item => {
                if (item.subtitle_path && item.proposed_path && item.status === 'ready') {
                    targets.push({
                        subtitle_path: item.subtitle_path,
                        proposed_path: item.proposed_path
                    });
                }
            });
        });
        
        if (targets.length === 0) {
            alert("동기화할 대상 자막 파일이 없습니다 (이미 모두 동기화 상태이거나 자막 매칭쌍이 없습니다).");
            return;
        }
        
        if (!confirm(`${targets.length}개의 자막 파일 이름을 동영상 파일명과 동일하게 변경하시겠습니까?`)) {
            return;
        }
        
        elements.btnExecuteSync.disabled = true;
        elements.btnExecuteSync.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> 적용 중...`;
        
        try {
            const response = await fetch('/api/match/execute', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ targets })
            });
            
            if (!response.ok) {
                throw new Error('자막 동기화 실행 중 오류가 발생했습니다.');
            }
            
            const result = await response.json();
            appendLog(`[SYSTEM] 자막 이름 변경 완료. 성공: ${result.success_count}개, 실패: ${result.fail_count}개`);
            
            if (result.fail_count > 0) {
                result.failures.forEach(f => {
                    appendLog(`[ERROR] 변경 실패 파일: ${f.source} -> ${f.error}`);
                });
            }
            
            // 미리보기 목록 갱신
            elements.previewSection.classList.add('hidden');
            state.previewGroups = [];
            
            // 폴더 브라우저 새로고침
            loadDirectory(state.currentPath);
            
        } catch (error) {
            appendLog(`[ERROR] 자막 동기화 실행 에러: ${error.message}`);
        } finally {
            elements.btnExecuteSync.disabled = false;
            elements.btnExecuteSync.innerHTML = `<i class="fa-solid fa-file-signature"></i> 자막 파일명 일괄 변경 적용`;
        }
    });

    // SMI to SRT 일괄 변환 실행
    elements.btnConvertRun.addEventListener('click', async () => {
        if (!state.selectedPath) return;
        
        const payload = {
            path: state.selectedPath,
            remove_original: elements.chkRemoveSmi.checked,
            output_format: elements.selSrtExt.value
        };
        
        appendLog(`[SYSTEM] SMI to SRT 일괄 변환 요청 전송됨: ${state.selectedPath}`);
        
        // 변환 UI 초기화
        const progressArea = document.getElementById('convert-progress-area');
        if (progressArea) {
            progressArea.classList.remove('hidden');
            document.getElementById('progress-percentage').textContent = '0%';
            document.getElementById('progress-text').textContent = '작업 대기 중...';
            document.getElementById('progress-bar-fill').style.width = '0%';
            document.getElementById('convert-result-summary').classList.add('hidden');
            document.getElementById('convert-fail-list-container').classList.add('hidden');
        }
        
        try {
            const response = await fetch('/api/convert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (!response.ok) {
                throw new Error('변환 요청 중 서버 에러가 발생했습니다.');
            }
            
            const result = await response.json();
            appendLog(`[SYSTEM] ${result.message}`);
            
        } catch (error) {
            appendLog(`[ERROR] SMI ➡️ SRT 일괄 변환 요청 실패: ${error.message}`);
        }
    });
}

// 5. 미리보기 테이블 렌더링 및 수동 정렬
function renderPreview() {
    elements.previewList.innerHTML = '';
    
    state.previewGroups.forEach((group, groupIdx) => {
        // 해당 폴더의 매칭 리스트 렌더링
        const groupEl = document.createElement('div');
        groupEl.classList.add('preview-folder-group');
        
        groupEl.innerHTML = `
            <div class="preview-folder-group-title">
                <i class="fa-solid fa-folder-open" style="color:#f59e0b; margin-right:8px;"></i>
                <span>${group.relative_path} (${group.dir_path})</span>
            </div>
            <table class="preview-table">
                <thead>
                    <tr>
                        <th style="width: 42%;">동영상 파일명</th>
                        <th style="width: 5%; text-align:center;"></th>
                        <th style="width: 38%;">자막 파일명 (변경 전 ➡️ 변경 후)</th>
                        <th style="width: 8%; text-align:center;">상태</th>
                        <th style="width: 7%; text-align:center;">정렬 조정</th>
                    </tr>
                </thead>
                <tbody id="group-body-${groupIdx}">
                    <!-- 행 동적 생성 -->
                </tbody>
            </table>
        `;
        
        elements.previewList.appendChild(groupEl);
        renderGroupRows(groupIdx);
    });
}

function renderGroupRows(groupIdx) {
    const tbody = document.getElementById(`group-body-${groupIdx}`);
    tbody.innerHTML = '';
    
    const group = state.previewGroups[groupIdx];
    
    group.matches.forEach((item, itemIdx) => {
        const tr = document.createElement('tr');
        
        // 상태 뱃지 HTML 생성
        let statusBadge = '';
        if (item.status === 'ready') {
            statusBadge = `<span class="status-badge status-ready">변경대기</span>`;
        } else if (item.status === 'synced') {
            statusBadge = `<span class="status-badge status-synced">동기화됨</span>`;
        } else {
            statusBadge = `<span class="status-badge status-unmatched">미매칭</span>`;
        }
        
        // 자막 셀 컨텐츠 구성
        let subtitleCell = '';
        if (item.subtitle_path) {
            if (item.status === 'ready') {
                subtitleCell = `
                    <div class="cell-subtitle">
                        <span class="sub-original">${item.subtitle_name}</span>
                        <span class="sub-proposed"><i class="fa-solid fa-right-long" style="margin-right:5px; font-size:0.75rem;"></i>${item.proposed_name}</span>
                    </div>
                `;
            } else {
                subtitleCell = `
                    <div class="cell-subtitle">
                        <span style="color:var(--text-secondary);">${item.subtitle_name}</span>
                    </div>
                `;
            }
        } else {
            subtitleCell = `<span style="color:var(--text-muted); font-style:italic;">자막 파일 없음</span>`;
        }
        
        // 정렬 조정 버튼 활성화/비활성화 결정 (자막이 없는 행이거나, 첫/끝 행 제어)
        const canMoveUp = item.subtitle_path && itemIdx > 0;
        // 다음 자막이 있는 행으로 보장
        const canMoveDown = item.subtitle_path && itemIdx < group.matches.length - 1;
        
        tr.innerHTML = `
            <td class="cell-video">${item.video_name || '<span style="color:var(--text-muted); font-style:italic;">동영상 파일 없음</span>'}</td>
            <td class="cell-arrow"><i class="fa-solid fa-link" style="opacity: ${item.video_path && item.subtitle_path ? 0.4 : 0}"></i></td>
            <td>${subtitleCell}</td>
            <td style="text-align:center;">${statusBadge}</td>
            <td class="cell-actions">
                <div class="action-row-buttons">
                    <button class="btn-move" title="자막 위로 이동" onclick="moveSubtitle(${groupIdx}, ${itemIdx}, -1)" ${canMoveUp ? '' : 'disabled'}>
                        <i class="fa-solid fa-chevron-up"></i>
                    </button>
                    <button class="btn-move" title="자막 아래로 이동" onclick="moveSubtitle(${groupIdx}, ${itemIdx}, 1)" ${canMoveDown ? '' : 'disabled'}>
                        <i class="fa-solid fa-chevron-down"></i>
                    </button>
                </div>
            </td>
        `;
        
        tbody.appendChild(tr);
    });
}

// 자막 행을 수동 스왑(위치 교정)하는 함수
window.moveSubtitle = function(groupIdx, itemIdx, direction) {
    const group = state.previewGroups[groupIdx];
    const targetIdx = itemIdx + direction;
    
    if (targetIdx < 0 || targetIdx >= group.matches.length) return;
    
    // 대상과 스왑할 자막 데이터 추출
    const currentItem = group.matches[itemIdx];
    const targetItem = group.matches[targetIdx];
    
    // 자막 정보들만 맞바꿈 (동영상 고정)
    const tempSubtitlePath = currentItem.subtitle_path;
    const tempSubtitleName = currentItem.subtitle_name;
    
    currentItem.subtitle_path = targetItem.subtitle_path;
    currentItem.subtitle_name = targetItem.subtitle_name;
    
    targetItem.subtitle_path = tempSubtitlePath;
    targetItem.subtitle_name = tempSubtitleName;
    
    // 스왑된 정보를 바탕으로 제안명(proposed_name)과 상태(status) 재조정
    updateItemMatchStatus(currentItem);
    updateItemMatchStatus(targetItem);
    
    // 최종 정렬 후 상태 갱신
    renderGroupRows(groupIdx);
    appendLog(`[SYSTEM] 수동 정렬 조정됨: [${group.relative_path}] 폴더 내의 에피소드 정렬 재배치`);
};

// --- SMI 변환 Progress UI 헬퍼 함수 ---
function updateProgressUI(data) {
    const progressArea = document.getElementById('convert-progress-area');
    if (!progressArea) return;
    
    const percentEl = document.getElementById('progress-percentage');
    const textEl = document.getElementById('progress-text');
    const fillEl = document.getElementById('progress-bar-fill');
    
    progressArea.classList.remove('hidden');
    document.getElementById('convert-result-summary').classList.add('hidden');
    document.getElementById('convert-fail-list-container').classList.add('hidden');
    
    const percent = Math.round((data.current / data.total) * 100) || 0;
    
    percentEl.textContent = `${percent}%`;
    textEl.textContent = `[${data.current} / ${data.total}] 변환 중: ${data.current_file}`;
    fillEl.style.width = `${percent}%`;
}

function showResultUI(data) {
    const progressArea = document.getElementById('convert-progress-area');
    if (!progressArea) return;
    
    const percentEl = document.getElementById('progress-percentage');
    const textEl = document.getElementById('progress-text');
    const fillEl = document.getElementById('progress-bar-fill');
    const summaryArea = document.getElementById('convert-result-summary');
    const failContainer = document.getElementById('convert-fail-list-container');
    const failList = document.getElementById('convert-fail-list');
    const badgeSuccess = document.getElementById('badge-success');
    const badgeFail = document.getElementById('badge-fail');
    
    progressArea.classList.remove('hidden');
    
    percentEl.textContent = '100%';
    textEl.textContent = '모든 파일 변환 처리가 완료되었습니다.';
    fillEl.style.width = '100%';
    
    summaryArea.classList.remove('hidden');
    badgeSuccess.textContent = `성공: ${data.success_count}`;
    badgeFail.textContent = `실패: ${data.fail_count}`;
    
    if (data.failures && data.failures.length > 0) {
        failContainer.classList.remove('hidden');
        failList.innerHTML = '';
        data.failures.forEach(f => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 500;">${f.file}</td>
                <td>
                    <div style="font-size: 0.8rem; color: var(--text-muted); margin-bottom: 4px;">${f.path}</div>
                    <div style="color: var(--danger);">${f.error}</div>
                </td>
            `;
            failList.appendChild(tr);
        });
    } else {
        failContainer.classList.add('hidden');
    }
}

// 스왑 후 항목의 제안된 이름 및 매칭 상태 다시 갱신
function updateItemMatchStatus(item) {
    if (item.video_path && item.subtitle_path) {
        const videoBase = item.video_name.substring(0, item.video_name.lastIndexOf('.')) || item.video_name;
        const subExt = item.subtitle_name.substring(item.subtitle_name.lastIndexOf('.')) || '';
        item.proposed_name = `${videoBase}${subExt}`;
        
        const dirPath = item.subtitle_path.substring(0, item.subtitle_path.lastIndexOf('/'));
        item.proposed_path = `${dirPath}/${item.proposed_name}`;
        
        if (item.subtitle_name === item.proposed_name) {
            item.status = 'synced';
        } else {
            item.status = 'ready';
        }
    } else {
        item.proposed_name = '';
        item.proposed_path = '';
        item.status = 'unmatched';
    }
}

// 앱 버전 로드 함수
async function loadAppVersion() {
    try {
        const response = await fetch('/api/version');
        if (response.ok) {
            const data = await response.json();
            if (elements.appVersion) {
                elements.appVersion.textContent = data.version;
            }
        }
    } catch (error) {
        console.error("Failed to load app version:", error);
    }
}
