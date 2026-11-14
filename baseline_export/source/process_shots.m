function process_shots(logsRoot, force)
%PROCESS_SHOTS  Process every shot under a logs folder into shot_NNNN.mat files.
%
%   process_shots                 run from the logs folder (or a day folder)
%   process_shots(logsRoot)       point at the logs folder
%   process_shots(logsRoot, true) reprocess everything
%
%   Works with the current ScopeDelayGUI session layout:
%     logs/<date>/experiment_log_<ts>/
%         shot_log_<ts>.csv        one row per shot (global shot number,
%                                  pressure, charge kV, BNC575 and laser DG535
%                                  timing, waveform filenames)
%         rigol1_<ts>.csv          shot 1 of the session
%         rigol1_<ts>_shot02.csv   later shots in the same session
%   and with the older July layout (no shot log, rigolN_<ts>.csv only).
%
%   Output, in <logsRoot>/processed_shots:
%     shot_NNNN.mat      one per shot, named by the global shot number
%                        (shot_<ts>.mat for old sessions without a shot log)
%     shot_summary.csv   one row per shot, opens in Excel
%
%   Every shot in the shot log gets a .mat, including dry runs and shots
%   whose waveform files were never written. S.status says which:
%     ok                 waveforms processed
%     no_fire            waveforms present, no pulse detected (dry run)
%     missing_waveforms  the shot log names files that do not exist
%     failed             processing raised an error (S.error has it)
%
%   A cached .mat is skipped if it is newer than this file, so editing the
%   pipeline reprocesses everything automatically.

if nargin < 1 || isempty(logsRoot), logsRoot = pwd; end
if nargin < 2, force = false; end

outDir = fullfile(logsRoot, 'processed_shots');
if ~exist(outDir, 'dir'), mkdir(outDir); end

sessions = find_sessions(logsRoot);
fprintf('found %d session folders under %s\n\n', numel(sessions), logsRoot);

me = dir([mfilename('fullpath') '.m']);
if isempty(me), myTime = 0; else, myTime = me(1).datenum; end

summary = {};
nOK = 0; nOther = 0; nSkip = 0; nFail = 0;

for i = 1:numel(sessions)
    sdir  = sessions{i};
    [~, folderName] = fileparts(sdir);
    stamp = strrep(folderName, 'experiment_log_', '');
    shots = session_shots(sdir, stamp);

    for j = 1:numel(shots)
        sh = shots(j);
        if isnan(sh.shot_number)
            key = ['shot_' stamp];
            if sh.session_shot_index > 1
                key = sprintf('%s_%02d', key, sh.session_shot_index);
            end
        else
            key = sprintf('shot_%04d', sh.shot_number);
        end
        matFile = fullfile(outDir, [key '.mat']);

        mf = dir(matFile);
        if ~force && ~isempty(mf) && mf(1).datenum > myTime
            S = load(matFile);
            summary(end+1, :) = summary_row(S); %#ok<AGROW>
            nSkip = nSkip + 1;
            continue;
        end

        S = struct();
        S.key = key;
        S.stamp = stamp;
        S.session_dir = sdir;
        S.shot_number = sh.shot_number;
        S.session_shot_index = sh.session_shot_index;
        S.files = sh.files;
        S.meta = sh.meta;
        S.settings = settings_from_meta(sh.meta);
        S.status = 'ok';
        S.error = '';
        S.peaks = struct();

        have = cellfun(@(f) exist(f, 'file') == 2, sh.files);
        if ~all(have)
            S.status = 'missing_waveforms';
            missing = sh.files(~have);
            [~, n1, e1] = fileparts(missing{1});
            S.error = sprintf('%d of 3 waveform files missing, first: %s%s', ...
                              sum(~have), n1, e1);
        else
            try
                W = process_waveforms(sh.files{1}, sh.files{2}, sh.files{3});
                fn = fieldnames(W);
                for q = 1:numel(fn), S.(fn{q}) = W.(fn{q}); end
            catch ME
                if ~isempty(strfind(ME.message, 'no pulse detected'))
                    S.status = 'no_fire';
                else
                    S.status = 'failed';
                end
                S.error = ME.message;
            end
        end

        % measured spacing, two independent ways, next to the commanded value
        S.spacing_rvm_ns = spacing_from_rvm(S);
        S.spacing_qsw_ns = spacing_from_qsw(S);

        save(matFile, '-struct', 'S');
        summary(end+1, :) = summary_row(S); %#ok<AGROW>

        switch S.status
            case 'ok'
                nOK = nOK + 1;
                fprintf('%s (%s): OK  D %0.f/%0.f  B %0.f/%0.f kV  spacing cmd %s / RVM %s / Qsw %s ns\n', ...
                    key, stamp, getpk(S,'LTGS1_Ddot'), getpk(S,'LTGS2_Ddot'), ...
                    getpk(S,'LTGS1_Bdot'), getpk(S,'LTGS2_Bdot'), ...
                    numtxt(S.settings.pulse_spacing_cmd_ns), ...
                    numtxt(S.spacing_rvm_ns), numtxt(S.spacing_qsw_ns));
            case 'failed'
                nFail = nFail + 1;
                fprintf(2, '%s (%s): FAILED (%s)\n', key, stamp, S.error);
            otherwise
                nOther = nOther + 1;
                fprintf('%s (%s): %s (%s)\n', key, stamp, S.status, S.error);
        end
    end
end

write_summary(fullfile(outDir, 'shot_summary.csv'), summary);
fprintf(['\ndone: %d processed, %d dry or missing, %d failed, %d cached\n' ...
         'summary: %s\n'], nOK, nOther, nFail, nSkip, ...
         fullfile(outDir, 'shot_summary.csv'));
end


%% ===================== session discovery =====================
function out = find_sessions(root)
% Every experiment_log_* folder at or below root. Written without '**' so
% it behaves the same on every MATLAB release.
out = {};
[~, here] = fileparts(root);
if strncmp(here, 'experiment_log_', 15)
    out = {root};
    return;
end
d = dir(root);
for k = 1:numel(d)
    if ~d(k).isdir || any(strcmp(d(k).name, {'.', '..', 'processed_shots'}))
        continue;
    end
    p = fullfile(root, d(k).name);
    if strncmp(d(k).name, 'experiment_log_', 15)
        out{end+1} = p; %#ok<AGROW>
    else
        out = [out, find_sessions(p)]; %#ok<AGROW>
    end
end
out = sort(out);
end


function shots = session_shots(sdir, stamp)
% One entry per shot in this session. Uses the shot log when it exists,
% otherwise treats the folder as one legacy shot.
shots = struct('shot_number', {}, 'session_shot_index', {}, ...
               'files', {}, 'meta', {});
logFile = fullfile(sdir, ['shot_log_' stamp '.csv']);

if exist(logFile, 'file') == 2
    [hdr, rows] = read_csv_text(logFile);
    for r = 1:numel(rows)
        meta = struct();
        vals = rows{r};
        for c = 1:numel(hdr)
            name = matlab_name(hdr{c});
            if c <= numel(vals), meta.(name) = vals{c}; else, meta.(name) = ''; end
        end
        idx = str2double(fieldor(meta, 'session_shot_index', '1'));
        if isnan(idx), idx = 1; end
        files = cell(1, 3);
        for k = 1:3
            nm = fieldor(meta, sprintf('rigol%d_file', k), '');
            if isempty(nm), nm = default_name(k, stamp, idx); end
            files{k} = fullfile(sdir, nm);
        end
        shots(end+1).shot_number = str2double(fieldor(meta, 'shot_number', '')); %#ok<AGROW>
        shots(end).session_shot_index = idx;
        shots(end).files = files;
        shots(end).meta = meta;
    end
    return;
end

% legacy session: no shot log, only the three CSVs
files = cell(1, 3);
for k = 1:3, files{k} = fullfile(sdir, default_name(k, stamp, 1)); end
if any(cellfun(@(f) exist(f, 'file') == 2, files))
    shots(1).shot_number = NaN;
    shots(1).session_shot_index = 1;
    shots(1).files = files;
    shots(1).meta = struct();
end
end


function nm = default_name(k, stamp, idx)
if idx > 1
    nm = sprintf('rigol%d_%s_shot%02d.csv', k, stamp, idx);
else
    nm = sprintf('rigol%d_%s.csv', k, stamp);
end
end


function [hdr, rows] = read_csv_text(f)
% Small quote-aware CSV reader. The shot log has about 100 columns mixing
% numbers, text and blanks. Reading everything as text and converting
% only the fields we use avoids readtable guessing a column type wrong.
txt = fileread(f);
txt = strrep(txt, sprintf('\r'), '');
lines = regexp(txt, '\n', 'split');
lines = lines(~cellfun(@isempty, lines));
hdr = split_csv_line(lines{1});
rows = cell(1, numel(lines) - 1);
for i = 2:numel(lines)
    rows{i-1} = split_csv_line(lines{i});
end
end


function out = split_csv_line(s)
out = {};
cur = '';
inq = false;
i = 1;
n = numel(s);
while i <= n
    ch = s(i);
    if inq
        if ch == '"'
            if i < n && s(i+1) == '"'
                cur(end+1) = '"'; i = i + 1; %#ok<AGROW>
            else
                inq = false;
            end
        else
            cur(end+1) = ch; %#ok<AGROW>
        end
    else
        if ch == '"'
            inq = true;
        elseif ch == ','
            out{end+1} = cur; cur = ''; %#ok<AGROW>
        else
            cur(end+1) = ch; %#ok<AGROW>
        end
    end
    i = i + 1;
end
out{end+1} = cur;
end


function name = matlab_name(h)
name = regexprep(strtrim(h), '[^A-Za-z0-9_]', '_');
if isempty(name) || ~isletter(name(1)), name = ['x' name]; end
name = name(1:min(end, namelengthmax));
end


function v = fieldor(s, f, dflt)
if isfield(s, f) && ~isempty(s.(f)), v = s.(f); else, v = dflt; end
end


function x = metanum(meta, f)
x = str2double(fieldor(meta, f, ''));
end


function st = settings_from_meta(meta)
% The shot-log values that matter for analysis, as numbers.
% NaN means the GUI did not know the value (or this is an old session).
st = struct();
st.datetime            = fieldor(meta, 'datetime', '');
st.pressure_psi        = metanum(meta, 'pressure_psi');
st.pressure_age_ms     = metanum(meta, 'pressure_age_ms');
st.wj1_charge_kv       = metanum(meta, 'wj1_charge_kv');
st.wj2_charge_kv       = metanum(meta, 'wj2_charge_kv');
st.wj1_program_kv      = metanum(meta, 'wj1_program_kv');
st.wj2_program_kv      = metanum(meta, 'wj2_program_kv');
st.pulse_spacing_cmd_ns = metanum(meta, 'pulse_spacing_ns');
st.bnc575_A_delay_us   = metanum(meta, 'bnc575_A_delay_us');
st.bnc575_B_delay_us   = metanum(meta, 'bnc575_B_delay_us');
chans = 'ABCD';
for c = chans
    st.(['dg535_' c '_delay_us']) = metanum(meta, ['dg535_laser_' c '_delay_us']);
    st.(['dg535_' c '_ref'])      = fieldor(meta, ['dg535_laser_' c '_ref'], '');
end
st.master_interlock_pass = metanum(meta, 'master_interlock_pass');
st.failed_interlocks     = fieldor(meta, 'failed_interlocks', '');
st.notes                 = fieldor(meta, 'notes', '');
end


%% ===================== measured spacing =====================
function sp = spacing_from_rvm(S)
% Time between the two RVM collapse edges (half-minimum crossing), in ns.
% Same method as the double-pulse GUI's spacing column.
sp = NaN;
if ~isfield(S, 'Rt') || numel(S.Rt) < 2, return; end
e = nan(1, 2);
for r = 1:2
    t = S.Rt{r};
    v = movmean(S.Rv{r}, 51);
    if isempty(v), continue; end
    [vmin, imin] = min(v);
    if vmin < -50
        thr = 0.5*vmin;
        j = find(v(imin:end) > thr, 1) + imin - 1;
        if ~isempty(j) && j > 1
            if v(j) == v(j-1), e(r) = t(j);
            else, e(r) = interp1(v(j-1:j), t(j-1:j), thr); end
        end
    end
end
sp = abs(e(2) - e(1))*1e3;
end


function sp = spacing_from_qsw(S)
% Laser 2 Q-switch rise minus laser 1 Q-switch rise, in ns.
% This is the timing the laser DG535 actually produced, and it should match
% the commanded pulse_spacing_ns from the shot log.
sp = NaN;
if isfield(S, 'peaks') && isfield(S.peaks, 't_Qsw1') && isfield(S.peaks, 't_Qsw2')
    sp = (S.peaks.t_Qsw2 - S.peaks.t_Qsw1)*1e3;
end
end


%% ===================== summary table =====================
function row = summary_row(S)
st = S.settings;
row = { ...
    S.shot_number, S.stamp, S.session_shot_index, st.datetime, S.status, ...
    st.pressure_psi, st.wj1_charge_kv, st.wj2_charge_kv, ...
    st.pulse_spacing_cmd_ns, S.spacing_qsw_ns, S.spacing_rvm_ns, ...
    getpk(S,'LTGS1_Ddot'), getpk(S,'LTGS2_Ddot'), ...
    getpk(S,'LTGS1_Bdot'), getpk(S,'LTGS2_Bdot'), ...
    getpk(S,'C225_Ddot'), getpk(S,'C315_Bdot'), ...
    getpk(S,'RVM1'), getpk(S,'RVM2'), ...
    getpk(S,'t_Qsw1'), getpk(S,'t_Qsw2'), ...
    vecget(S, 'rvm_gain', 1), vecget(S, 'rvm_gain', 2), ...
    scalarget(S, 'G_consistency'), ...
    st.master_interlock_pass, S.error};
end


function write_summary(f, rows)
hdr = {'shot_number','stamp','session_shot_index','datetime','status', ...
       'pressure_psi','wj1_charge_kv','wj2_charge_kv', ...
       'spacing_cmd_ns','spacing_qsw_ns','spacing_rvm_ns', ...
       'LTGS1_Ddot_kV','LTGS2_Ddot_kV','LTGS1_Bdot_kV','LTGS2_Bdot_kV', ...
       'C225_Ddot_kV','C315_Bdot_kV','RVM1_kV','RVM2_kV', ...
       't_Qsw1_us','t_Qsw2_us','rvm_gain_1','rvm_gain_2','G_consistency', ...
       'master_interlock_pass','error'};
fid = fopen(f, 'w');
if fid < 0, warning('could not write %s', f); return; end
fprintf(fid, '%s\n', strjoin(hdr, ','));
for r = 1:size(rows, 1)
    cells = cell(1, numel(hdr));
    for c = 1:numel(hdr)
        v = rows{r, c};
        if ischar(v)
            if any(v == ',') || any(v == '"')
                v = ['"' strrep(v, '"', '""') '"'];
            end
            cells{c} = v;
        elseif isempty(v) || (isnumeric(v) && isnan(v))
            cells{c} = '';
        else
            cells{c} = sprintf('%.6g', v);
        end
    end
    fprintf(fid, '%s\n', strjoin(cells, ','));
end
fclose(fid);
end


function v = getpk(S, f)
v = NaN;
if isfield(S, 'peaks') && isfield(S.peaks, f), v = S.peaks.(f); end
end

function v = vecget(S, f, k)
v = NaN;
if isfield(S, f) && numel(S.(f)) >= k, v = S.(f)(k); end
end

function v = scalarget(S, f)
v = NaN;
if isfield(S, f) && ~isempty(S.(f)), v = S.(f)(1); end
end

function s = numtxt(x)
if isempty(x) || isnan(x), s = '--'; else, s = sprintf('%.0f', x); end
end


%% ===================== waveform pipeline =====================
function S = process_waveforms(fr, fd, f3)
% The July double-pulse pipeline, unchanged in its math. Time axes in us,
% pulse 1 at t = 0.
%
% CONFIRM BEFORE TRUSTING NEW SHOTS: channel map and probe calibration are
% the July values. If any probe, divider or channel assignment changed
% since then, update these constants.

% rigol2
CF_CH1 = 1.85e11;    % CH1 = LTGS2-232 D-dot, FC011
CF_CH2 = -6.51e8;    % CH2 = LTGS2-007 B-dot, FC013
CF_CH3 = 1.83e11;    % CH3 = LTGS1-232 D-dot, FC017
CF_CH4 = -6.70e8;    % CH4 = LTGS1-007 B-dot, FC016
% rigol3
CF3_CH3 = -6.96e8;   % CH3 = C315 B-dot, FC027
CF3_CH4 = 1.56e11;   % CH4 = C225 D-dot, FC032
geom    = 2*pi*7.5;
bScale  = -5.5;
% rigol1 RVM dividers
DIV_CH1 = 19588.6/20000;
DIV_CH2 = 19970.7/20000;

Md = read_rigol(fd); td = Md(:,1);
M3 = read_rigol(f3); t3 = M3(:,1);
Mr = read_rigol(fr); tr = Mr(:,1);

% ---- detection ----
[s1, e1] = detect_activity(td, Md(:,4));
[s2, e2] = detect_activity(td, Md(:,5));
[s3, e3] = detect_activity(t3, M3(:,5));
starts = [s1 s2 s3]; ends = [e1 e2 e3];
if isempty(starts)
    error('no pulse detected on any anchor channel');
end
tPulse = median(starts);
tEnd   = max(ends);

% ---- windows ----
base_win   = [tPulse-8e-6, tPulse-4e-6];
droop_pre  = base_win;
droop_post = [tEnd+3e-6, min(tEnd+8e-6, td(end))];
int_win    = [tPulse-6e-6, droop_post(2)];
evt_win    = [tPulse-1e-6, tEnd+1e-6];
b_zero_win = [tPulse-0.3e-6, tPulse-0.05e-6];
b_int_win  = [b_zero_win(1), min(tEnd+8e-6, td(end))];
r3_pre  = [max(tPulse-2e-6, t3(1)+0.1e-6), tPulse-0.3e-6];
c3_zero = [max(tPulse-0.9e-6, t3(1)), tPulse-0.1e-6];
c3_int  = [c3_zero(1), t3(end)];

S = struct();
S.tPulse = tPulse; S.tEnd = tEnd;
S.peaks = struct();

% ---- D-dots (rigol2) ----
dcols = [4 2]; dCF = [CF_CH3 CF_CH1];
dtag  = {'LTGS1_Ddot','LTGS2_Ddot'};
S.Dt = cell(1,2); S.Dv = cell(1,2); S.Dv_raw = cell(1,2);
for k = 1:2
    v = remove_offset_step(td, Md(:,dcols(k)), base_win, droop_post, tPulse, tEnd);
    im = (td >= int_win(1)) & (td <= int_win(2));
    ti = td(im); vi = v(im);
    Vr = reconstruct(ti, vi, dCF(k), base_win, droop_pre, droop_post);
    S.Dt{k} = (ti - tPulse)*1e6;
    S.Dv_raw{k} = Vr/1e3;
end

% ---- B-dots (rigol2), Z*I ----
bcols = [5 3]; bCF = [CF_CH4 CF_CH2]*geom*bScale;
btag  = {'LTGS1_Bdot','LTGS2_Bdot'};
S.Bt = cell(1,2); S.Bv = cell(1,2);
for k = 1:2
    v = remove_offset_step(td, Md(:,bcols(k)), base_win, droop_post, tPulse, tEnd);
    im = (td >= b_int_win(1)) & (td <= b_int_win(2));
    ti = td(im); vi = v(im);
    Vr = reconstruct(ti, vi, bCF(k), b_zero_win, b_zero_win, droop_post);
    S.Bt{k} = (ti - tPulse)*1e6;
    S.Bv{k} = Vr/1e3;
    wm = (ti>evt_win(1)) & (ti<evt_win(2));
    S.peaks.(btag{k}) = max(abs(Vr(wm)))/1e3;
end

% ---- rigol3: C225 quiet-mask cubic, C315 pre-only ----
v = M3(:,5);
bm = (t3 > r3_pre(1)) & (t3 < r3_pre(2));
v  = v - mean(v(bm));
[~, ~, actMask] = detect_activity(t3, v);
padN = round(0.3e-6/(t3(2)-t3(1)));
actMask = movmax(double(actMask), 2*padN+1) > 0;
C225 = reconstruct_quiet(t3, v, CF3_CH4, c3_zero, actMask, 3);
S.C225_t = (t3 - tPulse)*1e6;
S.C225   = C225/1e3;
S.peaks.C225_Ddot = max(abs(C225))/1e3;

v = M3(:,4);
v = v - mean(v(bm));
im3 = (t3 >= c3_int(1)) & (t3 <= c3_int(2));
ti3 = t3(im3);
C315 = reconstruct_pre(ti3, v(im3), CF3_CH3*geom*bScale, c3_zero);
S.C315_t = (ti3 - tPulse)*1e6;
S.C315   = C315/1e3;
S.peaks.C315_Bdot = max(abs(C315))/1e3;

% ---- rigol3 Q-switch monitors (CH1 = Laser1, CH2 = Laser2) ----
qcols = [2 3]; qtag = {'Qsw1','Qsw2'};
S.Qt = cell(1,2); S.Qv = cell(1,2);
for k = 1:2
    vq = M3(:,qcols(k));
    [vg, tRise] = gate_qsw(t3, vq);
    S.Qt{k} = (t3 - tPulse)*1e6;
    S.Qv{k} = vg;
    if ~isnan(tRise)
        S.peaks.(['t_' qtag{k}]) = (tRise - tPulse)*1e6;
    else
        S.peaks.(['t_' qtag{k}]) = NaN;
    end
end

% ---- RVMs (rigol1), trimmed to the analysis span ----
rcols = [2 3]; rdiv = [DIV_CH1 DIV_CH2];
rtag  = {'RVM1','RVM2'};
S.Rt = cell(1,2); S.Rv = cell(1,2);
imr = (tr >= int_win(1)) & (tr <= int_win(2));
for k = 1:2
    v  = Mr(:,rcols(k));
    bm = (tr > base_win(1)) & (tr < base_win(2));
    Vr = rdiv(k) * (v - mean(v(bm)));
    S.Rt{k} = (tr(imr) - tPulse)*1e6;
    S.Rv{k} = Vr(imr)/1e3;
    wm = (tr>evt_win(1)) & (tr<evt_win(2));
    S.peaks.(rtag{k}) = max(abs(Vr(wm)))/1e3;
end

% ---- RVM-referenced baseline correction for the D-dots ----
S.rvm_gain = zeros(1,2); S.rvm_ref = zeros(1,2); S.rvm_rampRMS = zeros(1,2);
G = zeros(2,2);
for k = 1:2
    rampm = (S.Dt{k} > -3) & (S.Dt{k} < -0.2);
    bestRms = inf; Vref = [];
    for r = 1:2
        Vr0 = interp1(S.Rt{r}, S.Rv{r}, S.Dt{k}, 'linear', 'extrap');
        gg  = (Vr0(rampm)'*S.Dv_raw{k}(rampm)) / (Vr0(rampm)'*Vr0(rampm));
        G(k,r) = gg;
        rmsv = sqrt(mean((S.Dv_raw{k}(rampm) - gg*Vr0(rampm)).^2));
        if rmsv < bestRms
            bestRms = rmsv; Vref = gg*Vr0;
            S.rvm_gain(k) = gg; S.rvm_ref(k) = r;
        end
    end
    S.rvm_rampRMS(k) = bestRms;
    if S.rvm_gain(k) < 0.5 || S.rvm_gain(k) > 1.6 || bestRms > 60
        S.Dv{k} = S.Dv_raw{k};
        S.rvm_gain(k) = NaN;
    else
        dtu = S.Dt{k}(2) - S.Dt{k}(1);
        w = max(3, 2*floor(0.4/dtu)+1);
        c = movmean(S.Dv_raw{k} - Vref, w);
        gl = find(S.Dt{k} >= -0.3, 1);
        gh = find(S.Dt{k} >= (tEnd - tPulse)*1e6 + 0.8, 1);
        if isempty(gh), gh = numel(c); end
        c(gl:gh) = linspace(c(gl), c(gh), gh-gl+1)';
        S.Dv{k} = S.Dv_raw{k} - c;
    end
    wm = (S.Dt{k} > -1) & (S.Dt{k} < (tEnd-tPulse)*1e6 + 1);
    S.peaks.(dtag{k}) = max(abs(S.Dv{k}(wm)));
end

% ---- 2x2 gain factorization ----
if all(G(:) > 0)
    L = log(G);
    S.G = G;
    S.ddot_factor = exp(mean(L,2) - mean(L(:)))';
    S.rvm_factor  = exp(mean(L,1) - mean(L(:)));
    S.G_consistency = G(1,1)*G(2,2)/(G(1,2)*G(2,1));
else
    S.G = G;
    S.ddot_factor = [NaN NaN];
    S.rvm_factor  = [NaN NaN];
    S.G_consistency = NaN;
end
end


function M = read_rigol(f)
% Rigol export: time plus four channels. Handles both headers the GUI has
% written: "time_s,ch1_v,..." (July) and "Time (s),Voltage_CH1 (V),..."
% (current). Column order is the same in both.
M = readmatrix(f, 'NumHeaderLines', 1);
if size(M, 2) < 5
    error('%s has %d columns, expected time plus 4 channels', f, size(M, 2));
end
M = M(all(isfinite(M(:,1)), 2), :);
end


%% ===================== pipeline helpers =====================
% Same math as the July pipeline, except the gate_qsw pulse height (see
% below). gate_qsw finds the longest high run with
% diff() instead of a sample-by-sample loop: same result, much faster on
% 1,000,000-point records.
function [vg, tRise] = gate_qsw(t, v, min_dur, pad, thr_frac)
if nargin < 3, min_dur  = 100e-9; end
if nargin < 4, pad      = 60e-9;  end
if nargin < 5, thr_frac = 0.5;    end
dt  = t(2) - t(1);
lo  = median(v);
% Peak of a 20 ns moving mean, not the 98th percentile. On a 1,000,000-point
% record the ~1 us sync pulse is 0.25% of the samples, so the 98th
% percentile sits in the baseline noise. Same change as analysis/pipeline.py.
hi  = max(movmean(v, 2*round(20e-9/dt/2)+1));
vg  = zeros(size(v));
tRise = NaN;
if (hi - lo) < 0.3
    return;
end
thr   = lo + thr_frac*(hi - lo);
above = v > thr;
% longest sustained-high run, vectorized
d = diff([0; above(:); 0]);
runStart = find(d == 1);
runEnd   = find(d == -1) - 1;
if isempty(runStart), return; end
[bestLen, ib] = max(runEnd - runStart + 1);
if bestLen*dt < min_dur
    return;
end
bestA = runStart(ib); bestB = runEnd(ib);
padN = round(pad/dt);
a = max(1, bestA - padN);
b = min(numel(v), bestB + padN);
vg(a:b) = v(a:b) - lo;
tRise = t(bestA);
end

function [tS, tE, above] = detect_activity(t, v, k, env_s, noise_s)
if nargin < 3, k = 10;         end
if nargin < 4, env_s = 200e-9; end
if nargin < 5, noise_s = 500e-9; end
v0 = v - median(v);
dt = t(2) - t(1);
wn = max(8, round(noise_s/dt));
nb = floor(numel(v0)/wn);
blk = reshape(v0(1:nb*wn), wn, nb);
s = sort(std(blk, 0, 1));
sig = s(max(1, round(0.25*numel(s))));
env = movmax(abs(v0), max(3, round(env_s/dt)));
above = env > k*sig;
if ~any(above), tS = []; tE = []; return; end
tS = t(find(above, 1, 'first'));
tE = t(find(above, 1, 'last'));
end

function vc = remove_offset_step(t, v, pre_win, post_win, tPulse, tEnd)
vp = mean(v((t > pre_win(1))  & (t < pre_win(2))));
vq = mean(v((t > post_win(1)) & (t < post_win(2))));
off = vp*ones(size(v));
r = (t >= tPulse) & (t <= tEnd);
off(r) = vp + (vq - vp).*(t(r) - tPulse)./(tEnd - tPulse);
off(t > tEnd) = vq;
vc = v - off;
end

function Vr = reconstruct(ti, vi, CF, zero_win, droop_pre, droop_post)
integ = cumtrapz(ti, vi);
pm = ((ti>droop_pre(1))&(ti<droop_pre(2))) | ((ti>droop_post(1))&(ti<droop_post(2)));
p  = polyfit(ti(pm), integ(pm), 1);
integ = integ - polyval(p, ti);
zm = (ti > zero_win(1)) & (ti < zero_win(2));
integ = integ - mean(integ(zm));
Vr = CF * integ;
end

function Vr = reconstruct_quiet(ti, vi, CF, zero_win, act_mask, deg)
integ = cumtrapz(ti, vi);
q = ~act_mask;
[p, ~, mu] = polyfit(ti(q), integ(q), deg);
integ = integ - polyval(p, ti, [], mu);
zm = (ti > zero_win(1)) & (ti < zero_win(2));
integ = integ - mean(integ(zm));
Vr = CF * integ;
end

function Ir = reconstruct_pre(ti, vi, CF, pre_win)
integ = cumtrapz(ti, vi);
zm = (ti > pre_win(1)) & (ti < pre_win(2));
p  = polyfit(ti(zm), integ(zm), 1);
Ir = CF * (integ - polyval(p, ti));
end
