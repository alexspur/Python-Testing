function results = nanovna_cable(files, opts)
%NANOVNA_CABLE  Delay, velocity factor, loss and match from NanoVNA S2P files.
%
%   results = nanovna_cable()                    pick .s2p files in a dialog
%   results = nanovna_cable('Load_CVR.s2p')      one file
%   results = nanovna_cable('C:\data\*.s2p')     every file matching a pattern
%   results = nanovna_cable(files, opts)         override defaults (see below)
%
%   Setup this assumes (Oct 30 calibration):
%     CH0 (S11 port): SOL at the SMA port face, then an SMA to BNC female
%                     adapter. The cable BNC end plugs in here.
%     CH1 (S21 port): jumper, SMA barrel, SMA to N female adapter.
%     Thru step:      N male to BNC male adapter between the two.
%   So S21 is referenced to the thru adapter. Its one-way delay is added back
%   to every cable. The CH0 BNC adapter delay is removed from S11 for the TDR.
%   Both delays come from two reference S1P files saved with the BNC adapter
%   on CH0: one bare (adapter_open.s1p), one with the thru adapter on it and
%   its N end open (adapter_thru_open.s1p).
%
%   Delay: straight-line fit to the unwrapped S21 phase over opts.fitBand_MHz.
%   This averages out the point-to-point noise in the app's group delay plot.
%
%   No toolboxes required.
%
%   Options (struct fields, all optional):
%     length_ft        physical length, ft. Scalar for all files, or a vector
%                      with one entry per file. NaN skips VF.  default 40
%     openRef          S1P, BNC adapter bare on CH0     default 'adapter_open.s1p'
%     thruOpenRef      S1P, thru adapter open on CH0    default 'adapter_thru_open.s1p'
%     thruDelay_ns     use this instead of the files    default [] (use files)
%     bncDelay_ns      use this instead of the files    default [] (use files)
%     fitBand_MHz      phase fit band                   default [1 290]
%     lossFreqs_MHz    loss table frequencies           default [10 100 300 450 900]
%     plot             one figure per cable             default true
%     csvOut           results CSV path, '' to skip     default ''
%
%   Output columns:
%     File, Length_m, Delay_ns (one way, adapter corrected), VF,
%     IL_<f>MHz_dB (insertion loss), IL_<f>MHz_dB_per_100ft,
%     LossFit_a, LossFit_b  (IL dB ~ a*sqrt(f_MHz) + b*f_MHz),
%     S11_worst_dB, S11_median_dB

    if nargin < 1 || isempty(files)
        [fn, pn] = uigetfile('*.s2p', 'Select S2P files', 'MultiSelect', 'on');
        if isequal(fn, 0), results = []; return; end
        files = fullfile(pn, cellstr(fn));
    end
    if ischar(files) || (exist('isstring', 'builtin') && isstring(files))
        files = char(files);
        if any(files == '*')
            d = dir(files);
            files = cellfun(@(n) fullfile(fileparts(files), n), {d.name}, ...
                            'UniformOutput', false);
        else
            files = {files};
        end
    end
    if nargin < 2, opts = struct(); end
    opts = setDefaults(opts);

    c   = 299792458;
    nF  = numel(files);
    Lft = opts.length_ft(:).';
    if isscalar(Lft), Lft = repmat(Lft, 1, nF); end
    Lm  = Lft * 0.3048;

    % ---- adapter delays from the reference files -------------------------
    [tBnc, tThru] = adapterDelays(files{1}, opts);
    fprintf('CH0 BNC adapter, one way: %.1f ps\n', tBnc * 1e12);
    fprintf('Thru adapter, one way:    %.1f ps (added to every cable)\n\n', ...
            tThru * 1e12);

    lf = opts.lossFreqs_MHz(:).';
    R  = struct([]);

    for k = 1:nF
        [f, S] = readTouchstone(files{k});
        s11 = S(:, 1);
        s21 = S(:, 2);

        % Delay: fit phase = -2*pi*f*tau + phi0 over the fit band
        ph = unwrap(angle(s21));
        m  = f >= opts.fitBand_MHz(1)*1e6 & f <= opts.fitBand_MHz(2)*1e6;
        p  = polyfit(f(m), ph(m), 1);
        tau = -p(1) / (2*pi) + tThru;

        % Loss
        IL  = -20 * log10(abs(s21));
        m2  = f >= 5e6;
        A   = [sqrt(f(m2)/1e6), f(m2)/1e6];
        ab  = A \ IL(m2);

        [~, base, ext] = fileparts(files{k});
        R(k).File      = [base ext];
        R(k).Length_m  = Lm(k);
        R(k).Delay_ns  = tau * 1e9;
        R(k).VF        = Lm(k) / (c * tau);
        for j = 1:numel(lf)
            [~, i] = min(abs(f - lf(j)*1e6));
            tag = strrep(sprintf('%g', lf(j)), '.', 'p');
            R(k).(['IL_' tag 'MHz_dB'])           = IL(i);
            R(k).(['IL_' tag 'MHz_dB_per_100ft']) = IL(i) / Lft(k) * 100;
        end
        R(k).LossFit_a     = ab(1);
        R(k).LossFit_b     = ab(2);
        s11dB = 20 * log10(abs(s11(f >= 1e6)));
        R(k).S11_worst_dB  = max(s11dB);
        R(k).S11_median_dB = median(s11dB);

        fprintf('%-30s  delay %8.3f ns   VF %.4f   IL %s dB at %s MHz\n', ...
            R(k).File, R(k).Delay_ns, R(k).VF, ...
            mat2str(round(arrayfun(@(F) IL(nearest(f, F*1e6)), lf) * 100) / 100), ...
            mat2str(lf));

        if opts.plot
            plotCable(f, s11, s21, IL, ab, tau, tThru, tBnc, R(k), opts);
        end
    end

    if exist('struct2table', 'file') || exist('struct2table', 'builtin')
        results = struct2table(R);
        if ~isempty(opts.csvOut), writetable(results, opts.csvOut); end
    else
        results = R;   % Octave fallback
    end
end

% =========================================================================
function opts = setDefaults(opts)
    def = struct('length_ft', 40, 'openRef', 'adapter_open.s1p', ...
                 'thruOpenRef', 'adapter_thru_open.s1p', ...
                 'thruDelay_ns', [], 'bncDelay_ns', [], ...
                 'fitBand_MHz', [1 290], ...
                 'lossFreqs_MHz', [10 100 300 450 900], ...
                 'plot', true, 'csvOut', '');
    fn = fieldnames(def);
    for k = 1:numel(fn)
        if ~isfield(opts, fn{k}), opts.(fn{k}) = def.(fn{k}); end
    end
end

% =========================================================================
function [tBnc, tThru] = adapterDelays(firstFile, opts)
    % Reference files are looked for next to the data, then on the path.
    here = fileparts(firstFile);
    if ~isempty(opts.bncDelay_ns)
        tBnc = opts.bncDelay_ns * 1e-9;
    else
        tBnc = reflDelay(findRef(opts.openRef, here)) / 2;
    end
    if ~isempty(opts.thruDelay_ns)
        tThru = opts.thruDelay_ns * 1e-9;
    else
        tBoth = reflDelay(findRef(opts.thruOpenRef, here)) / 2;
        tThru = tBoth - tBnc;
    end
end

function p = findRef(name, here)
    if exist(fullfile(here, name), 'file'), p = fullfile(here, name);
    elseif exist(name, 'file'),             p = name;
    else, error('Reference file %s not found. Set opts.%s or the delay directly.', ...
                name, 'openRef / thruOpenRef');
    end
end

function tRT = reflDelay(fname)
    % Round-trip delay of an open-ended adapter from its S11 phase slope.
    % Fit below the 300 MHz harmonic crossover.
    [f, S] = readTouchstone(fname);
    m  = f > 1e6 & f < 290e6;
    p  = polyfit(f(m), unwrap(angle(S(m, 1))), 1);
    tRT = -p(1) / (2*pi);
end

% =========================================================================
function [f, S] = readTouchstone(fname)
    % Touchstone v1 reader for 1-port and 2-port files.
    % Returns S as [S11 S21 S12 S22] for 2-port, S11 for 1-port.
    % Handles RI, MA, DB and Hz/kHz/MHz/GHz.
    txt   = fileread(fname);
    lines = regexp(txt, '\r?\n', 'split');
    fmt = 'MA'; mult = 1e9;
    data = [];
    for k = 1:numel(lines)
        L = strtrim(lines{k});
        if isempty(L) || L(1) == '!', continue; end
        b = find(L == '!', 1);
        if ~isempty(b), L = strtrim(L(1:b-1)); end
        if L(1) == '#'
            tok = upper(strsplit(strtrim(L(2:end))));
            for t = 1:numel(tok)
                switch tok{t}
                    case 'HZ',  mult = 1;
                    case 'KHZ', mult = 1e3;
                    case 'MHZ', mult = 1e6;
                    case 'GHZ', mult = 1e9;
                    case {'RI', 'MA', 'DB'}, fmt = tok{t};
                end
            end
            continue
        end
        v = sscanf(L, '%f').';
        if numel(v) >= 3, data(end+1, 1:numel(v)) = v; end %#ok<AGROW>
    end
    f = data(:, 1) * mult;
    nS = floor((size(data, 2) - 1) / 2);
    S = zeros(numel(f), nS);
    for n = 1:nS
        a = data(:, 2*n); b = data(:, 2*n + 1);
        switch fmt
            case 'RI', S(:, n) = a + 1i*b;
            case 'MA', S(:, n) = a .* exp(1i*deg2rad(b));
            case 'DB', S(:, n) = 10.^(a/20) .* exp(1i*deg2rad(b));
        end
    end
end

function i = nearest(f, F)
    [~, i] = min(abs(f - F));
end

% =========================================================================
function [d, Z] = tdrImpedance(f, s11, tBnc, VF)
    % Low-pass step TDR from CH0, with the BNC adapter delay removed.
    c   = 299792458;
    s11 = s11 .* exp(1i * 2*pi * f * 2 * tBnc);
    df  = median(diff(f));
    N   = round(f(end) / df);
    fg  = (1:N).' * df;
    sg  = interp1(f, real(s11), fg, 'linear', 'extrap') + ...
          1i * interp1(f, imag(s11), fg, 'linear', 'extrap');
    S   = [real(s11(1)); sg];
    M   = 2*N; nn = (N:M).';
    w   = besseli(0, 6 * sqrt(1 - ((2*nn - M)/M).^2)) / besseli(0, 6);
    S   = S .* w;
    nfft = 16384;
    X = zeros(nfft, 1); X(1:N+1) = S; X(end-N+1:end) = conj(flipud(S(2:end)));
    h = real(ifft(X));
    rho = cumsum(h);
    Z = 50 * (1 + rho) ./ (1 - rho);
    t = (0:nfft-1).' / (nfft * df);
    d = c * VF * t / 2;
end

% =========================================================================
function plotCable(f, s11, s21, IL, ab, tau, tThru, tBnc, r, opts)
    fM = f / 1e6;
    figure('Name', r.File, 'Color', 'w');

    subplot(2, 2, 1)
    plot(fM, IL, 'LineWidth', 1.2); hold on
    plot(fM, ab(1)*sqrt(fM) + ab(2)*fM, '--', 'LineWidth', 1);
    grid on; xlabel('Frequency (MHz)', 'Interpreter', 'none');
    ylabel('Insertion loss (dB)', 'Interpreter', 'none');
    title(sprintf('Loss, fit %.4f*sqrt(f) + %.5f*f', ab(1), ab(2)), 'Interpreter', 'none');
    legend({'Measured', 'Fit'}, 'Location', 'northwest', 'Interpreter', 'none');

    subplot(2, 2, 2)
    plot(fM, 20*log10(abs(s11)), 'LineWidth', 1);
    grid on; xlabel('Frequency (MHz)', 'Interpreter', 'none');
    ylabel('|S11| (dB)', 'Interpreter', 'none');
    title('Match from BNC end', 'Interpreter', 'none');

    subplot(2, 2, 3)
    % Smoothed group delay: sliding linear fit of phase over ~20 MHz
    ph = unwrap(angle(s21));
    df = median(diff(f)); w = max(5, round(20e6 / df));
    gd = nan(size(f));
    for i = 1:numel(f)
        j = max(1, i - w):min(numel(f), i + w);
        q = polyfit(f(j), ph(j), 1);
        gd(i) = -q(1) / (2*pi) + tThru;
    end
    plot(fM, gd * 1e9, 'LineWidth', 1); hold on
    plot([fM(1) fM(end)], tau * 1e9 * [1 1], '--', 'LineWidth', 1);
    grid on; xlabel('Frequency (MHz)', 'Interpreter', 'none');
    ylabel('Group delay (ns)', 'Interpreter', 'none');
    title(sprintf('Delay %.3f ns one way', tau * 1e9), 'Interpreter', 'none');
    ylim(tau * 1e9 + [-1.5 1.5]);

    subplot(2, 2, 4)
    VF = r.VF; if ~isfinite(VF), VF = 0.66; end
    [d, Z] = tdrImpedance(f, s11, tBnc, VF);
    m = d <= 1.3 * max(r.Length_m, c_len(tau, VF));
    plot(d(m), Z(m), 'LineWidth', 1.2);
    grid on; xlabel(sprintf('Distance from BNC end (m), VF = %.3f', VF), 'Interpreter', 'none');
    ylabel('Impedance (ohm)', 'Interpreter', 'none');
    title('TDR impedance', 'Interpreter', 'none');
    ylim([30 70]);

    if exist('sgtitle', 'file') || exist('sgtitle', 'builtin')
        sgtitle(r.File, 'Interpreter', 'none');
    end
end

function L = c_len(tau, VF)
    L = 299792458 * VF * tau;
end