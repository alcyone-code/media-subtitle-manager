// Media Subtitles Manager Client Logic

// 애플리케이션 상태 관리
const state = {
    currentPath: '/media',
    parentPath: '',
    selectedPath: null,
    previewGroups: [], // 폴더 단위 매칭 미리보기 원본 데이터
    previewModel: [],  // 동영상 단위로 재구성한 미리보기 데이터
    excludedSubtitles: new Set(), // 이름 변경에서 제외할 자막 경로
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
    initPreviewEvents();
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
            state.excludedSubtitles = new Set();
            state.previewModel = buildPreviewModel(state.previewGroups);
            refreshMatchStatuses(state.previewModel, null);

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
        if (state.previewModel.length === 0) return;

        // 체크되어 있고 변경 대기 상태인 자막만 대상으로 추출
        const targets = [];
        state.previewModel.forEach((group) => {
            collectGroupSubtitles(group).forEach((item) => {
                if (item.status !== 'ready' || !item.proposed_path) return;
                if (state.excludedSubtitles.has(item.subtitle_path)) return;
                targets.push({
                    subtitle_path: item.subtitle_path,
                    proposed_path: item.proposed_path
                });
            });
        });
        
        if (targets.length === 0) {
            alert("변경할 자막이 선택되지 않았습니다. 자막을 체크하거나 다시 분석해 주세요.");
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
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.detail || '자막 동기화 실행 중 오류가 발생했습니다.');
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
            state.previewModel = [];
            state.excludedSubtitles.clear();
            
            // 폴더 브라우저 새로고침
            loadDirectory(state.currentPath);
            
        } catch (error) {
            appendLog(`[ERROR] 자막 동기화 실행 에러: ${error.message}`);
        } finally {
            updatePreviewSummary();
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

// 5. 미리보기 렌더링 (동영상 단위 그룹)
const MATCH_METHOD_LABELS = {
    basename: '파일명 일치',
    episode: '회차 일치',
    order: '순서 기준',
    manual: '수동 조정'
};

const STATUS_LABELS = {
    ready: '변경대기',
    synced: '동기화됨',
    conflict: '중복 이름',
    unmatched: '미매칭'
};

function escapeHtml(value) {
    const text = (value === null || value === undefined) ? '' : String(value);
    return text.replace(/[&<>"']/g, (ch) => ({
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#39;'
    }[ch]));
}

function stripExtension(name) {
    const idx = name.lastIndexOf('.');
    return idx > 0 ? name.substring(0, idx) : name;
}

function extensionOf(name) {
    const idx = name.lastIndexOf('.');
    return idx > 0 ? name.substring(idx) : '';
}

function directoryOf(path) {
    const idx = Math.max(path.lastIndexOf('/'), path.lastIndexOf('\\'));
    return idx >= 0 ? path.substring(0, idx) : '';
}

function joinPath(directory, name) {
    if (!directory) return name;
    const separator = directory.includes('\\') ? '\\' : '/';
    return `${directory}${separator}${name}`;
}

function naturalCompare(a, b) {
    return String(a).localeCompare(String(b), undefined, { numeric: true, sensitivity: 'base' });
}

// 백엔드의 폴더별 매칭 결과(행 목록)를 "동영상 1개 + 자막 여러 개" 구조로 변환
function buildPreviewModel(groups) {
    return groups.map((group) => {
        const videos = [];
        const videoIndex = new Map();
        const orphans = [];

        group.matches.forEach((row) => {
            if (!row.video_path) {
                orphans.push(row);
                return;
            }
            let video = videoIndex.get(row.video_path);
            if (!video) {
                video = { video_path: row.video_path, video_name: row.video_name, subtitles: [] };
                videoIndex.set(row.video_path, video);
                videos.push(video);
            }
            if (row.subtitle_path) {
                video.subtitles.push(row);
            }
        });

        videos.forEach((video) => {
            video.subtitles.sort((a, b) => naturalCompare(a.subtitle_name, b.subtitle_name));
        });

        return {
            dir_path: group.dir_path,
            relative_path: group.relative_path,
            videos: videos,
            orphans: orphans
        };
    });
}

function collectGroupSubtitles(group) {
    const subtitles = [];
    group.videos.forEach((video) => subtitles.push(...video.subtitles));
    subtitles.push(...group.orphans);
    return subtitles;
}

function collectAllSubtitles(model) {
    return model.reduce((acc, group) => acc.concat(collectGroupSubtitles(group)), []);
}

function renderPreview() {
    // 다시 그려도 스크롤 위치가 유지되도록 한다 (수동 이동/체크 시 화면이 튀지 않게)
    const container = elements.previewList.parentElement;
    const scrollTop = container ? container.scrollTop : 0;

    elements.previewList.innerHTML = '';
    state.previewModel.forEach((group, groupIdx) => {
        elements.previewList.appendChild(renderFolderGroup(group, groupIdx));
    });
    updatePreviewSummary();

    if (container) container.scrollTop = scrollTop;
}

function renderFolderGroup(group, groupIdx) {
    const subtitles = collectGroupSubtitles(group);
    const counts = { ready: 0, synced: 0, conflict: 0, unmatched: 0 };
    subtitles.forEach((row) => {
        counts[row.status] = (counts[row.status] || 0) + 1;
    });

    const readyCount = counts.ready;
    const selectedCount = subtitles.filter(
        (row) => row.status === 'ready' && !state.excludedSubtitles.has(row.subtitle_path)
    ).length;
    const allSelected = readyCount > 0 && selectedCount === readyCount;

    const stats = [
        `<span class="stat-chip"><strong>${group.videos.length}</strong> 영상</span>`,
        `<span class="stat-chip"><strong>${subtitles.length}</strong> 자막</span>`
    ];
    if (counts.ready) stats.push(`<span class="stat-chip ready"><strong>${counts.ready}</strong> 변경</span>`);
    if (counts.synced) stats.push(`<span class="stat-chip synced"><strong>${counts.synced}</strong> 동기화</span>`);
    if (counts.conflict) stats.push(`<span class="stat-chip conflict"><strong>${counts.conflict}</strong> 중복</span>`);
    if (counts.unmatched) stats.push(`<span class="stat-chip unmatched"><strong>${counts.unmatched}</strong> 미매칭</span>`);

    const videoCards = group.videos
        .map((video, videoIdx) => renderVideoCard(groupIdx, video, videoIdx, group.videos.length))
        .join('');
    const orphanCard = group.orphans.length ? renderOrphanCard(group.orphans) : '';

    const groupEl = document.createElement('div');
    groupEl.className = 'preview-folder-group';
    groupEl.innerHTML = `
        <div class="preview-folder-header">
            <div class="folder-title" title="${escapeHtml(group.dir_path)}">
                <i class="fa-solid fa-folder-open"></i>
                <span>${escapeHtml(group.relative_path)}</span>
            </div>
            <div class="folder-stats">${stats.join('')}</div>
            <label class="select-all-label" title="이 폴더의 변경 대상 전체 선택/해제">
                <input type="checkbox" data-action="select-all" data-group="${groupIdx}"
                    ${allSelected ? 'checked' : ''} ${readyCount ? '' : 'disabled'}>
                전체 선택
            </label>
        </div>
        <div class="video-list">${videoCards}${orphanCard}</div>
    `;
    return groupEl;
}

function renderVideoCard(groupIdx, video, videoIdx, videoCount) {
    const subtitleRows = video.subtitles.length
        ? video.subtitles
            .map((row) => renderSubtitleRow(groupIdx, row, videoIdx, videoCount))
            .join('')
        : `<div class="video-empty"><i class="fa-solid fa-ban"></i> 연결된 자막 없음</div>`;

    return `
        <div class="video-card">
            <div class="video-card-header">
                <i class="fa-solid fa-film"></i>
                <span class="video-name" title="${escapeHtml(video.video_name)}">${escapeHtml(video.video_name)}</span>
                <span class="video-count">자막 ${video.subtitles.length}개</span>
            </div>
            ${subtitleRows}
        </div>
    `;
}

function renderSubtitleRow(groupIdx, row, videoIdx, videoCount) {
    const canSelect = row.status === 'ready';
    const isSelected = canSelect && !state.excludedSubtitles.has(row.subtitle_path);
    const statusLabel = STATUS_LABELS[row.status] || row.status;
    const methodLabel = MATCH_METHOD_LABELS[row.match_method] || '';

    const proposed = (row.proposed_name && row.status !== 'synced')
        ? `<span class="sub-proposed"><i class="fa-solid fa-arrow-right sub-arrow"></i>${escapeHtml(row.proposed_name)}</span>`
        : '';

    const checkbox = canSelect
        ? `<input type="checkbox" class="sub-check" data-action="toggle" data-sub="${escapeHtml(row.subtitle_path)}" ${isSelected ? 'checked' : ''}>`
        : `<span class="check-placeholder"></span>`;

    return `
        <div class="subtitle-row ${canSelect && !isSelected ? 'excluded' : ''}">
            ${checkbox}
            <div class="sub-names">
                <span class="sub-original">${escapeHtml(row.subtitle_name)}</span>
                ${proposed}
            </div>
            <span class="status-badge status-${row.status}">${statusLabel}</span>
            ${methodLabel ? `<span class="method-badge">${methodLabel}</span>` : ''}
            <div class="sub-actions">
                <button class="btn-move" data-action="move" data-group="${groupIdx}"
                    data-sub="${escapeHtml(row.subtitle_path)}" data-dir="-1"
                    title="이전 동영상으로 이동" ${videoIdx === 0 ? 'disabled' : ''}>
                    <i class="fa-solid fa-arrow-up"></i>
                </button>
                <button class="btn-move" data-action="move" data-group="${groupIdx}"
                    data-sub="${escapeHtml(row.subtitle_path)}" data-dir="1"
                    title="다음 동영상으로 이동" ${videoIdx >= videoCount - 1 ? 'disabled' : ''}>
                    <i class="fa-solid fa-arrow-down"></i>
                </button>
            </div>
        </div>
    `;
}

function renderOrphanCard(orphans) {
    const rows = orphans
        .map((row) => `
            <div class="subtitle-row">
                <span class="check-placeholder"></span>
                <div class="sub-names"><span class="sub-original">${escapeHtml(row.subtitle_name)}</span></div>
                <span class="status-badge status-unmatched">동영상 없음</span>
            </div>
        `)
        .join('');

    return `
        <div class="video-card">
            <div class="video-card-header">
                <i class="fa-solid fa-triangle-exclamation"></i>
                <span class="video-name">동영상이 없는 자막</span>
                <span class="video-count">${orphans.length}개</span>
            </div>
            ${rows}
        </div>
    `;
}

// 6. 미리보기 상호작용 (선택 / 수동 이동)
function initPreviewEvents() {
    elements.previewList.addEventListener('click', (event) => {
        const button = event.target.closest('button[data-action="move"]');
        if (!button) return;
        moveSubtitleToVideo(
            Number(button.dataset.group),
            button.dataset.sub,
            Number(button.dataset.dir)
        );
    });

    elements.previewList.addEventListener('change', (event) => {
        const input = event.target;
        if (input.matches('input[data-action="toggle"]')) {
            if (input.checked) {
                state.excludedSubtitles.delete(input.dataset.sub);
            } else {
                state.excludedSubtitles.add(input.dataset.sub);
            }
            renderPreview();
        } else if (input.matches('input[data-action="select-all"]')) {
            const group = state.previewModel[Number(input.dataset.group)];
            if (!group) return;
            collectGroupSubtitles(group)
                .filter((row) => row.status === 'ready')
                .forEach((row) => {
                    if (input.checked) {
                        state.excludedSubtitles.delete(row.subtitle_path);
                    } else {
                        state.excludedSubtitles.add(row.subtitle_path);
                    }
                });
            renderPreview();
        }
    });
}

function moveSubtitleToVideo(groupIdx, subtitlePath, direction) {
    const group = state.previewModel[groupIdx];
    if (!group) return;

    const currentIndex = group.videos.findIndex((video) =>
        video.subtitles.some((row) => row.subtitle_path === subtitlePath)
    );
    if (currentIndex === -1) return;

    const targetIndex = currentIndex + direction;
    if (targetIndex < 0 || targetIndex >= group.videos.length) return;

    const source = group.videos[currentIndex];
    const target = group.videos[targetIndex];
    const rowIndex = source.subtitles.findIndex((row) => row.subtitle_path === subtitlePath);
    const [row] = source.subtitles.splice(rowIndex, 1);

    row.video_path = target.video_path;
    row.video_name = target.video_name;
    target.subtitles.push(row);
    target.subtitles.sort((a, b) => naturalCompare(a.subtitle_name, b.subtitle_name));

    refreshMatchStatuses(state.previewModel, subtitlePath);
    renderPreview();
    appendLog(`[SYSTEM] 수동 조정: ${row.subtitle_name} → ${target.video_name}`);

    const movedRow = target.subtitles.find((item) => item.subtitle_path === subtitlePath);
    if (movedRow && movedRow.status === 'conflict') {
        appendLog(
            `[WARN] ${movedRow.subtitle_name}: 대상 동영상에 같은 이름으로 변경될 자막이 있어 변경 대상에서 제외했습니다.`
        );
    }
}

function refreshMatchStatuses(model, manualSubtitlePath) {
    const allSubtitles = collectAllSubtitles(model);

    allSubtitles.forEach((row) => {
        if (row.video_path && row.subtitle_path) {
            const videoBase = stripExtension(row.video_name);
            const langSuffix = getSubtitleLangSuffix(row.subtitle_name);
            const subExt = extensionOf(row.subtitle_name);
            row.proposed_name = `${videoBase}${langSuffix}${subExt}`;
            row.proposed_path = joinPath(directoryOf(row.subtitle_path), row.proposed_name);
            row.status = row.subtitle_name === row.proposed_name ? 'synced' : 'ready';
            if (manualSubtitlePath && row.subtitle_path === manualSubtitlePath) {
                row.match_method = 'manual';
            }
        } else {
            row.proposed_name = '';
            row.proposed_path = '';
            row.status = 'unmatched';
            row.match_method = 'unmatched';
        }
    });

    // 같은 이름으로 변경되는 자막은 충돌로 표시 (백엔드와 동일한 규칙)
    const claims = new Map();
    allSubtitles.forEach((row) => {
        if (!row.proposed_path) return;
        const key = row.proposed_path.toLowerCase();
        if (!claims.has(key)) claims.set(key, []);
        claims.get(key).push(row);
    });

    claims.forEach((claimedRows) => {
        if (claimedRows.length < 2) return;
        const alreadySynced = claimedRows.find((row) => row.subtitle_name === row.proposed_name);
        const losers = alreadySynced
            ? claimedRows.filter((row) => row !== alreadySynced)
            : claimedRows;
        losers.forEach((row) => {
            row.status = 'conflict';
            row.proposed_name = '';
            row.proposed_path = '';
        });
    });
}

function updatePreviewSummary() {
    const subtitles = collectAllSubtitles(state.previewModel);
    const readySubtitles = subtitles.filter((row) => row.status === 'ready');
    const selectedSubtitles = readySubtitles.filter(
        (row) => !state.excludedSubtitles.has(row.subtitle_path)
    );

    elements.txtPreviewCount.textContent = `자막 ${readySubtitles.length}개 변경 예정`;
    elements.btnExecuteSync.disabled = selectedSubtitles.length === 0;
    elements.btnExecuteSync.innerHTML = selectedSubtitles.length
        ? `<i class="fa-solid fa-file-signature"></i> 선택한 자막 ${selectedSubtitles.length}개 이름 변경`
        : `<i class="fa-solid fa-file-signature"></i> 변경할 자막이 없습니다`;
}

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
function getSubtitleLangSuffix(subtitleName) {
    // 백엔드(_get_subtitle_lang_suffix)와 동일한 규칙: .ko, .en 등 언어 코드 유지
    const languageCodes = ['ko', 'kor', 'kr', 'en', 'eng', 'ja', 'jpn', 'jp', 'zh', 'zho', 'chi', 'chs', 'cht', 'sc', 'tc'];
    const stem = subtitleName.substring(0, subtitleName.lastIndexOf('.')) || subtitleName;
    const match = stem.match(/\.([A-Za-z]{2,3})$/);
    if (match && languageCodes.includes(match[1].toLowerCase())) {
        return match[0];
    }
    return '';
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
