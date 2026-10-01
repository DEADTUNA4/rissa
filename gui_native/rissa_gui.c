/* rissa native GUI — Win32 C frontend, Python backend untouched.
 *
 * Why Win32 and not OpenGL/Vulkan: for a file-compressor utility window
 * (buttons, file pickers, log view) OpenGL/Vulkan only add a GPU driver +
 * windowing dependency (GLFW/SDL) and MORE memory, not less. Plain Win32
 * User32/GDI has zero extra DLLs and the smallest possible footprint.
 * The Python backend (tools/rissa_tool.py frozen as rissa-tool.exe, which
 * itself bundles the C kernels c_shuffle/c_bit/c_delta) is spawned as a
 * child process — not modified, not reimplemented.
 *
 * Build with w64devkit (GCC 16.2):
 *   E:\w64devkit\bin\gcc.exe -O2 -municode -mwindows rissa_gui.c -o rissa_gui.exe -lgdi32 -lcomdlg32 -lcomctl32
 * Or just run build.bat in this folder.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <commdlg.h>
#include <shellapi.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define IDC_EDIT_IN    101
#define IDC_EDIT_OUT   102
#define IDC_BTN_BIN    103
#define IDC_BTN_BOUT   104
#define IDC_COMBO_BLK  105
#define IDC_CHK_DICT   106
#define IDC_CHK_FAST   107
#define IDC_BTN_COMP   108
#define IDC_BTN_DECOMP 109
#define IDC_BTN_DOCTOR 110
#define IDC_BTN_SITE   111
#define IDC_LOG        112
#define IDC_PROG       113
#define IDC_STATUS     114
#define IDC_BTN_DISCORD 115

#define DISCORD_URL L"https://discord.gg/wzpwcCv92j"

#ifndef PBM_SETMARQUEE
#define PBM_SETMARQUEE (WM_USER + 10)
#endif

/* MS _snwprintf does NOT null-terminate on truncation: always terminate.
 * Only for stack arrays (not pointers). */
#define SNWPRINTF(buf, ...) do { \
    _snwprintf(buf, (sizeof(buf) / sizeof((buf)[0])), __VA_ARGS__); \
    (buf)[(sizeof(buf) / sizeof((buf)[0])) - 1] = L'\0'; \
} while (0)

static HINSTANCE g_hInst;
static HWND g_hIn, g_hOut, g_hBlk, g_hDict, g_hFast, g_hLog, g_hProg, g_hStatus;
static HWND g_hComp, g_hDecomp, g_hDoctor;
static HFONT g_hFont;
static wchar_t g_backend[MAX_PATH] = L"";
static volatile BOOL g_running = FALSE;
static FILE *g_logFile = NULL;

/* ---- log helpers (widget + rissa_gui.log file for Discord bug reports) ---- */
static void LogFileW(const wchar_t *s) {
    if (!g_logFile) return;
    int n = WideCharToMultiByte(CP_UTF8, 0, s, -1, NULL, 0, NULL, NULL);
    if (n <= 0) return;
    char *b = (char *)malloc((size_t)n);
    if (!b) return;
    WideCharToMultiByte(CP_UTF8, 0, s, -1, b, n, NULL, NULL);
    fwrite(b, 1, (size_t)n - 1, g_logFile);
    fflush(g_logFile);
    free(b);
}

static void LogAppendW(const wchar_t *s) {
    LogFileW(s);
    int len = GetWindowTextLengthW(g_hLog);
    SendMessageW(g_hLog, EM_SETSEL, (WPARAM)len, (LPARAM)len);
    SendMessageW(g_hLog, EM_REPLACESEL, (WPARAM)FALSE, (LPARAM)s);
    SendMessageW(g_hLog, EM_SCROLLCARET, 0, 0);
}

static void LogAppendA_Utf8(const char *s) {
    /* backend prints plain ASCII; try UTF-8 then fall back to ACP */
    int n = MultiByteToWideChar(CP_UTF8, 0, s, -1, NULL, 0);
    if (n <= 0) n = MultiByteToWideChar(CP_ACP, 0, s, -1, NULL, 0);
    if (n <= 0) return;
    wchar_t *w = (wchar_t *)malloc((size_t)n * sizeof(wchar_t));
    if (!w) return;
    if (MultiByteToWideChar(CP_UTF8, 0, s, -1, w, n) <= 0)
        MultiByteToWideChar(CP_ACP, 0, s, -1, w, n);
    LogAppendW(w);
    free(w);
}

static void SetRunning(BOOL on) {
    g_running = on;
    EnableWindow(g_hComp, !on);
    EnableWindow(g_hDecomp, !on);
    EnableWindow(g_hDoctor, !on);
    SendMessageW(g_hProg, PBM_SETMARQUEE, (WPARAM)on, (LPARAM)30);
    ShowWindow(g_hProg, on ? SW_SHOW : SW_HIDE);
}

/* ---- backend location ---- */
static BOOL FileExistsW(const wchar_t *p) {
    DWORD a = GetFileAttributesW(p);
    return (a != INVALID_FILE_ATTRIBUTES) && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

static void FindBackend(void) {
    wchar_t dir[MAX_PATH];
    GetModuleFileNameW(NULL, dir, MAX_PATH);
    wchar_t *slash = wcsrchr(dir, L'\\');
    if (slash) *slash = L'\0';

    const wchar_t *cands[4];
    wchar_t c0[MAX_PATH], c1[MAX_PATH], c2[MAX_PATH];
    /* 1. next to this exe */
    SNWPRINTF(c0, L"%s\\rissa-tool.exe", dir);
    /* 2. ../dist/rissa-tool.exe (dev layout: gui_native/ + dist/) */
    SNWPRINTF(c1, L"%s\\..\\dist\\rissa-tool.exe", dir);
    /* 3. dist/rissa-tool.exe (launched from repo root) */
    SNWPRINTF(c2, L"%s\\dist\\rissa-tool.exe", dir);
    cands[0] = c0; cands[1] = c1; cands[2] = c2; cands[3] = L"rissa-tool.exe"; /* 4. on PATH */

    for (int i = 0; i < 4; i++) {
        if (i < 3) {
            wchar_t full[MAX_PATH];
            if (!GetFullPathNameW(cands[i], MAX_PATH, full, NULL)) continue;
            if (FileExistsW(full)) { wcscpy(g_backend, full); return; }
        } else {
            /* PATH lookup */
            wchar_t found[MAX_PATH];
            DWORD n = SearchPathW(NULL, L"rissa-tool.exe", NULL, MAX_PATH, found, NULL);
            if (n > 0 && n < MAX_PATH) { wcscpy(g_backend, found); return; }
        }
    }
    g_backend[0] = L'\0';
}

/* ---- quoting ---- */
static void AppendQuoted(wchar_t *dst, size_t cap, const wchar_t *s) {
    size_t n = wcslen(dst);
    if (n + 3 >= cap) return;
    dst[n++] = L'"';
    for (const wchar_t *p = s; *p && n + 2 < cap; p++) {
        if (*p == L'"') { dst[n++] = L'\\'; }
        dst[n++] = *p;
    }
    dst[n++] = L'"';
    dst[n] = L'\0';
}

/* ---- worker thread: spawn backend, stream output to log ---- */
static DWORD WINAPI BackendThread(LPVOID param) {
    wchar_t *cmd = (wchar_t *)param; /* malloc'd by caller */
    SECURITY_ATTRIBUTES sa = { sizeof(sa), NULL, TRUE };
    HANDLE hRead = NULL, hWrite = NULL;
    if (!CreatePipe(&hRead, &hWrite, &sa, 0)) {
        LogAppendW(L"[gui] CreatePipe failed\r\n");
        free(cmd);
        SetRunning(FALSE);
        return 1;
    }
    SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    si.hStdOutput = hWrite;
    si.hStdError = hWrite;
    si.hStdInput = NULL; /* child needs no stdin; don't inherit ours */
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    ZeroMemory(&pi, sizeof(pi));

    LogAppendW(L"> ");
    LogAppendW(cmd);
    LogAppendW(L"\r\n");

    if (!CreateProcessW(NULL, cmd, NULL, NULL, TRUE,
                        CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        wchar_t e[128];
        SNWPRINTF(e, L"[gui] failed to launch backend (err %lu)\r\n", GetLastError());
        LogAppendW(e);
        CloseHandle(hWrite);
        CloseHandle(hRead);
        free(cmd);
        SetRunning(FALSE);
        return 1;
    }
    CloseHandle(hWrite);
    hWrite = NULL;

    char buf[4096];
    DWORD got = 0;
    for (;;) {
        BOOL ok = ReadFile(hRead, buf, sizeof(buf) - 1, &got, NULL);
        if (!ok || got == 0) break;
        buf[got] = '\0';
        LogAppendA_Utf8(buf);
    }
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 0;
    GetExitCodeProcess(pi.hProcess, &code);
    wchar_t done[128];
    SNWPRINTF(done, L"[gui] exit code %lu\r\n", code);
    LogAppendW(done);

    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    CloseHandle(hRead);
    free(cmd);
    SetRunning(FALSE);
    return 0;
}

static void StartBackend(const wchar_t *cmdline) {
    if (g_running) { LogAppendW(L"[gui] busy — wait for current job\r\n"); return; }
    if (!g_backend[0]) { LogAppendW(L"[gui] backend not found (rissa-tool.exe)\r\n"); return; }
    size_t n = wcslen(cmdline) + 1;
    wchar_t *copy = (wchar_t *)malloc(n * sizeof(wchar_t));
    if (!copy) return;
    wcscpy(copy, cmdline);
    SetRunning(TRUE);
    HANDLE h = CreateThread(NULL, 0, BackendThread, copy, 0, NULL);
    if (!h) { free(copy); SetRunning(FALSE); LogAppendW(L"[gui] CreateThread failed\r\n"); return; }
    CloseHandle(h);
}

static int GetBlockSize(void) {
    int idx = (int)SendMessageW(g_hBlk, CB_GETCURSEL, 0, 0);
    wchar_t t[32] = L"65536";
    if (idx != CB_ERR) SendMessageW(g_hBlk, CB_GETLBTEXT, (WPARAM)idx, (LPARAM)t);
    return _wtoi(t) > 0 ? _wtoi(t) : 65536;
}

static void OnCompress(void) {
    wchar_t in[MAX_PATH], out[MAX_PATH];
    GetWindowTextW(g_hIn, in, MAX_PATH);
    GetWindowTextW(g_hOut, out, MAX_PATH);
    if (!in[0] || !out[0]) { MessageBoxW(NULL, L"Pick input and output files.", L"rissa", MB_ICONWARNING); return; }
    wchar_t cmd[4 * MAX_PATH + 128];
    cmd[0] = L'\0';
    AppendQuoted(cmd, 4 * MAX_PATH + 128, g_backend);
    wcscat(cmd, L" compress ");
    AppendQuoted(cmd, 4 * MAX_PATH + 128, in);
    wcscat(cmd, L" -o ");
    AppendQuoted(cmd, 4 * MAX_PATH + 128, out);
    wchar_t b[64];
    SNWPRINTF(b, L" --block %d", GetBlockSize());
    wcscat(cmd, b);
    if (SendMessageW(g_hDict, BM_GETCHECK, 0, 0) == BST_CHECKED) wcscat(cmd, L" --dict");
    if (SendMessageW(g_hFast, BM_GETCHECK, 0, 0) == BST_CHECKED) wcscat(cmd, L" --fast");
    StartBackend(cmd);
}

static void OnDecompress(void) {
    wchar_t in[MAX_PATH], out[MAX_PATH];
    GetWindowTextW(g_hIn, in, MAX_PATH);
    GetWindowTextW(g_hOut, out, MAX_PATH);
    if (!in[0] || !out[0]) { MessageBoxW(NULL, L"Pick input and output files.", L"rissa", MB_ICONWARNING); return; }
    wchar_t cmd[4 * MAX_PATH + 64];
    cmd[0] = L'\0';
    AppendQuoted(cmd, 4 * MAX_PATH + 64, g_backend);
    wcscat(cmd, L" decompress ");
    AppendQuoted(cmd, 4 * MAX_PATH + 64, in);
    wcscat(cmd, L" -o ");
    AppendQuoted(cmd, 4 * MAX_PATH + 64, out);
    StartBackend(cmd);
}

static void OnDoctor(void) {
    wchar_t cmd[2 * MAX_PATH + 32];
    cmd[0] = L'\0';
    AppendQuoted(cmd, 2 * MAX_PATH + 32, g_backend);
    wcscat(cmd, L" doctor");
    StartBackend(cmd);
}

static BOOL BrowseFile(HWND owner, BOOL save, wchar_t *out, DWORD cap, const wchar_t *filter) {
    OPENFILENAMEW ofn;
    ZeroMemory(&ofn, sizeof(ofn));
    ofn.lStructSize = sizeof(ofn);
    ofn.hwndOwner = owner;
    ofn.lpstrFile = out;
    ofn.nMaxFile = cap;
    ofn.lpstrFilter = filter;
    ofn.nFilterIndex = 1;
    ofn.Flags = OFN_PATHMUSTEXIST | OFN_OVERWRITEPROMPT | OFN_NOCHANGEDIR;
    if (save) return GetSaveFileNameW(&ofn);
    /* open mode: file must exist */
    ofn.Flags = OFN_FILEMUSTEXIST | OFN_PATHMUSTEXIST | OFN_NOCHANGEDIR;
    return GetOpenFileNameW(&ofn);
}

static void SuggestOutput(void) {
    wchar_t in[MAX_PATH];
    GetWindowTextW(g_hIn, in, MAX_PATH);
    if (!in[0]) return;
    wchar_t cur[MAX_PATH];
    GetWindowTextW(g_hOut, cur, MAX_PATH);
    if (cur[0]) return; /* don't overwrite user's choice */
    size_t n = wcslen(in);
    if (n + 7 >= MAX_PATH) return;
    if (n > 6 && _wcsicmp(in + n - 6, L".rissa") == 0) {
        wcsncpy(cur, in, n - 6);
        cur[n - 6] = L'\0';
    } else {
        wcscpy(cur, in);
        wcscat(cur, L".rissa");
    }
    SetWindowTextW(g_hOut, cur);
}

/* ---- window ---- */
static LRESULT CALLBACK WndProc(HWND h, UINT m, WPARAM w, LPARAM l) {
    switch (m) {
    case WM_COMMAND: {
        int id = LOWORD(w);
        if (id == IDC_BTN_BIN) {
            wchar_t p[MAX_PATH] = L"";
            if (BrowseFile(h, FALSE, p, MAX_PATH, L"All files\0*.*\0rissa archives\0*.rissa\0")) {
                SetWindowTextW(g_hIn, p);
                SuggestOutput();
            }
        } else if (id == IDC_BTN_BOUT) {
            wchar_t p[MAX_PATH] = L"";
            GetWindowTextW(g_hOut, p, MAX_PATH);
            if (BrowseFile(h, TRUE, p, MAX_PATH, L"rissa archives\0*.rissa\0All files\0*.*\0"))
                SetWindowTextW(g_hOut, p);
        } else if (id == IDC_BTN_COMP) OnCompress();
        else if (id == IDC_BTN_DECOMP) OnDecompress();
        else if (id == IDC_BTN_DOCTOR) OnDoctor();
        else if (id == IDC_BTN_DISCORD) ShellExecuteW(NULL, L"open", DISCORD_URL, NULL, NULL, SW_SHOWNORMAL);
        else if (id == IDC_BTN_SITE) ShellExecuteW(NULL, L"open", L"https://rissa.web.app", NULL, NULL, SW_SHOWNORMAL);
        return 0;
    }
    case WM_CLOSE:
        if (g_running) {
            if (MessageBoxW(h, L"A job is running. Quit anyway?", L"rissa",
                            MB_YESNO | MB_ICONQUESTION) != IDYES)
                return 0;
        }
        DestroyWindow(h);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, LPWSTR lpCmd, int nShow) {
    (void)hPrev; (void)lpCmd;
    g_hInst = hInst;

    INITCOMMONCONTROLSEX icc = { sizeof(icc), ICC_PROGRESS_CLASS };
    InitCommonControlsEx(&icc);

    WNDCLASSW wc;
    ZeroMemory(&wc, sizeof(wc));
    wc.lpfnWndProc = WndProc;
    wc.hInstance = hInst;
    wc.hCursor = LoadCursor(NULL, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_BTNFACE + 1);
    wc.lpszClassName = L"RissaGui";
    RegisterClassW(&wc);

    HWND h = CreateWindowExW(0, L"RissaGui", L"rissa — Rissanen MDL 1978",
        WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX,
        CW_USEDEFAULT, CW_USEDEFAULT, 640, 500,
        NULL, NULL, hInst, NULL);
    if (!h) return 1;

    g_hFont = CreateFontW(-12, 0, 0, 0, FW_NORMAL, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");
    HFONT hFontBold = CreateFontW(-19, 0, 0, 0, FW_BOLD, FALSE, FALSE, FALSE,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, L"Segoe UI");

    /* layout: fixed positions */
    HWND hdr = CreateWindowExW(0, L"STATIC", L"rissa",
        WS_CHILD | WS_VISIBLE | SS_CENTER, 10, 6, 604, 30, h, NULL, hInst, NULL);
    CreateWindowExW(0, L"STATIC", L"Context-Selecting Compression  |  native Win32 frontend — backend unchanged",
        WS_CHILD | WS_VISIBLE | SS_CENTER, 10, 34, 604, 18, h, NULL, hInst, NULL);

    CreateWindowExW(0, L"STATIC", L"Input:", WS_CHILD | WS_VISIBLE,
        14, 62, 50, 22, h, NULL, hInst, NULL);
    g_hIn = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 66, 60, 430, 24, h, (HMENU)IDC_EDIT_IN, hInst, NULL);
    CreateWindowExW(0, L"BUTTON", L"Browse…",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 502, 59, 108, 26, h, (HMENU)IDC_BTN_BIN, hInst, NULL);

    CreateWindowExW(0, L"STATIC", L"Output:", WS_CHILD | WS_VISIBLE,
        14, 92, 50, 22, h, NULL, hInst, NULL);
    g_hOut = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | ES_AUTOHSCROLL, 66, 90, 430, 24, h, (HMENU)IDC_EDIT_OUT, hInst, NULL);
    CreateWindowExW(0, L"BUTTON", L"Browse…",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 502, 89, 108, 26, h, (HMENU)IDC_BTN_BOUT, hInst, NULL);

    CreateWindowExW(0, L"STATIC", L"Block:", WS_CHILD | WS_VISIBLE,
        14, 124, 50, 22, h, NULL, hInst, NULL);
    g_hBlk = CreateWindowExW(0, L"COMBOBOX", NULL,
        WS_CHILD | WS_VISIBLE | CBS_DROPDOWNLIST | WS_VSCROLL, 66, 122, 120, 120,
        h, (HMENU)IDC_COMBO_BLK, hInst, NULL);
    const wchar_t *blks[] = { L"4096", L"16384", L"65536", L"131072" };
    for (int i = 0; i < 4; i++) SendMessageW(g_hBlk, CB_ADDSTRING, 0, (LPARAM)blks[i]);
    SendMessageW(g_hBlk, CB_SETCURSEL, 2, 0); /* 65536 default, same as Tkinter GUI */

    g_hDict = CreateWindowExW(0, L"BUTTON", L"Shared Dict (1MB->64KB)",
        WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX, 200, 122, 200, 24, h, (HMENU)IDC_CHK_DICT, hInst, NULL);
    g_hFast = CreateWindowExW(0, L"BUTTON", L"Fast (~10x, skip BWT)",
        WS_CHILD | WS_VISIBLE | BS_AUTOCHECKBOX, 410, 122, 200, 24, h, (HMENU)IDC_CHK_FAST, hInst, NULL);

    g_hComp = CreateWindowExW(0, L"BUTTON", L"Compress",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 14, 152, 112, 30, h, (HMENU)IDC_BTN_COMP, hInst, NULL);
    g_hDecomp = CreateWindowExW(0, L"BUTTON", L"Decompress",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 132, 152, 112, 30, h, (HMENU)IDC_BTN_DECOMP, hInst, NULL);
    g_hDoctor = CreateWindowExW(0, L"BUTTON", L"Doctor",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 250, 152, 112, 30, h, (HMENU)IDC_BTN_DOCTOR, hInst, NULL);
    CreateWindowExW(0, L"BUTTON", L"Discord",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 368, 152, 112, 30, h, (HMENU)IDC_BTN_DISCORD, hInst, NULL);
    CreateWindowExW(0, L"BUTTON", L"rissa.web.app",
        WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, 486, 152, 124, 30, h, (HMENU)IDC_BTN_SITE, hInst, NULL);

    g_hProg = CreateWindowExW(0, PROGRESS_CLASSW, NULL,
        WS_CHILD | PBS_MARQUEE, 14, 190, 596, 14, h, (HMENU)IDC_PROG, hInst, NULL);
    ShowWindow(g_hProg, SW_HIDE);

    g_hLog = CreateWindowExW(WS_EX_CLIENTEDGE, L"EDIT", L"",
        WS_CHILD | WS_VISIBLE | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL |
        WS_VSCROLL | WS_HSCROLL, 14, 210, 596, 200, h, (HMENU)IDC_LOG, hInst, NULL);
    g_hStatus = CreateWindowExW(0, L"STATIC", L"",
        WS_CHILD | WS_VISIBLE, 14, 416, 596, 36, h, (HMENU)IDC_STATUS, hInst, NULL);

    /* one pass over all children covers inputs, buttons, labels, log, status */
    {
        HWND ch = GetWindow(h, GW_CHILD);
        while (ch) { SendMessageW(ch, WM_SETFONT, (WPARAM)g_hFont, TRUE); ch = GetWindow(ch, GW_HWNDNEXT); }
    }
    SendMessageW(hdr, WM_SETFONT, (WPARAM)hFontBold, TRUE); /* keep header bold */

    FindBackend();
    /* open run log next to this exe (bug reports: paste it on Discord) */
    {
        wchar_t exedir[MAX_PATH], logp[MAX_PATH];
        GetModuleFileNameW(NULL, exedir, MAX_PATH);
        wchar_t *sl = wcsrchr(exedir, L'\\');
        if (sl) *sl = L'\0';
        _snwprintf(logp, MAX_PATH, L"%s\\rissa_gui.log", exedir);
        logp[(sizeof(logp) / sizeof(logp[0])) - 1] = L'\0';
        g_logFile = _wfopen(logp, L"ab"); /* raw UTF-8 bytes via LogFileW */
        if (g_logFile) {
            static int wrote_bom = 0;
            if (!wrote_bom) {
                long sz = 0;
                fseek(g_logFile, 0, SEEK_END);
                sz = ftell(g_logFile);
                if (sz == 0) fwrite("\xEF\xBB\xBF", 1, 3, g_logFile);
                wrote_bom = 1;
            }
        }
    }
    if (g_backend[0]) {
        wchar_t st[2 * MAX_PATH + 32];
        SNWPRINTF(st, L"Backend: %s", g_backend);
        SetWindowTextW(g_hStatus, st);
        LogAppendW(L"[gui] native Win32 frontend ready. Backend untouched.\r\n");
        LogAppendW(L"[gui] bugs? paste rissa_gui.log (next to this exe) on Discord: https://discord.gg/wzpwcCv92j\r\n");
        LogAppendW(L"[gui] ");
        LogAppendW(g_backend);
        LogAppendW(L"\r\n");
    } else {
        SetWindowTextW(g_hStatus, L"Backend NOT FOUND — put rissa_gui.exe next to rissa-tool.exe or in gui_native/ (uses ../dist/rissa-tool.exe).");
        LogAppendW(L"[gui] backend NOT FOUND. Copy rissa_gui.exe next to rissa-tool.exe\r\n"
                   L"      or keep it in gui_native/ so ../dist/rissa-tool.exe resolves.\r\n");
    }

    ShowWindow(h, nShow);
    UpdateWindow(h);

    MSG msg;
    while (GetMessageW(&msg, NULL, 0, 0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (g_logFile) fclose(g_logFile);
    DeleteObject(g_hFont);
    DeleteObject(hFontBold);
    return (int)msg.wParam;
}
