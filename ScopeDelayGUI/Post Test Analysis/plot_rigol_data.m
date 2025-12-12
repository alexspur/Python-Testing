%% Plot Rigol Scope Data - Time-Aligned, Savitzky-Golay Filtered
% This script plots rigol1 and rigol2 data in subplots with dual y-axes
% - Automatically detects fall start and time-aligns signals
% - Applies Savitzky-Golay filter (best for pulse signals)
% - Uses common x-axis range based on shorter time scale
% 
% Channel Names:
%   Scope 1 Ch1: RVM 1 (scaled: /20000 * 19588.6, converted to kV)
%   Scope 1 Ch2: CVR
%   Scope 2 Ch1: RVM 2 (scaled: * 19970.7, converted to kV)
%   Scope 2 Ch2: Trigger Generator Sync Output

clear; clc; close all;

%% ===================== CONFIGURATION =====================
% Set the test folder path
testFolder = 'C:\Users\ESpurbeck\Desktop\LANL Project\Marx Testing\Testing\12.11.25\Test_07_6_psi_91.7%_of_self_break_so_55kV_only_took_one_fire_command';

% Scaling factors
RVM1_scale = 19588.6 / 20000;  % Divide by 20000, multiply by 19588.6
RVM2_scale = 19970.7;          % Multiply by 19970.7

% Savitzky-Golay filter parameters
% - window_length: must be ODD, larger = more smoothing
% - polyorder: polynomial order (2 or 3 typical for pulse signals)
sgWindowLength = 15;  % Adjust this (must be odd): 11-21 typical range
sgPolyOrder = 3;      % Polynomial order: 3 works well for preserving peaks

% Fall detection parameters
smoothingWindow = 10;

%% ===================== FIND FILES =====================
rigol1Files = dir(fullfile(testFolder, '*rigol1*.csv'));
rigol2Files = dir(fullfile(testFolder, '*rigol2*.csv'));

if isempty(rigol1Files) || isempty(rigol2Files)
    error('Could not find rigol1 or rigol2 CSV files in: %s', testFolder);
end

rigol1File = fullfile(testFolder, rigol1Files(1).name);
rigol2File = fullfile(testFolder, rigol2Files(1).name);

fprintf('Loading: %s\n', rigol1Files(1).name);
fprintf('Loading: %s\n', rigol2Files(1).name);

%% ===================== LOAD DATA =====================
data1 = readtable(rigol1File);
data2 = readtable(rigol2File);

% Extract raw data - Rigol 1
time1 = data1.time_s * 1e6;  % Convert to microseconds
RVM1_raw = data1.ch1_v * RVM1_scale / 1000;  % Apply scaling, convert to kV
CVR_raw = data1.ch2_v;

% Extract raw data - Rigol 2
time2 = data2.time_s * 1e6;  % Convert to microseconds
RVM2_raw = data2.ch1_v * RVM2_scale / 1000;  % Apply scaling, convert to kV
TrigSync_raw = data2.ch2_v;

%% ===================== APPLY SAVITZKY-GOLAY FILTER =====================
% Savitzky-Golay is ideal for pulse signals because it:
% - Preserves peak amplitudes
% - Preserves rise/fall times
% - No phase distortion or ringing
% - Fits polynomials to follow actual signal shape

fprintf('\n=== Applying Savitzky-Golay Filter ===\n');
fprintf('Window length: %d, Polynomial order: %d\n', sgWindowLength, sgPolyOrder);

RVM1 = sgolayfilt(RVM1_raw, sgPolyOrder, sgWindowLength);
CVR = sgolayfilt(CVR_raw, sgPolyOrder, sgWindowLength);
RVM2 = sgolayfilt(RVM2_raw, sgPolyOrder, sgWindowLength);
TrigSync = sgolayfilt(TrigSync_raw, sgPolyOrder, sgWindowLength);

% Show peak preservation
fprintf('\n=== Peak Value Comparison ===\n');
fprintf('RVM1: Raw min = %.2f kV, Filtered min = %.2f kV (%.1f%% preserved)\n', ...
    min(RVM1_raw), min(RVM1), 100*min(RVM1)/min(RVM1_raw));
fprintf('RVM2: Raw min = %.2f kV, Filtered min = %.2f kV (%.1f%% preserved)\n', ...
    min(RVM2_raw), min(RVM2), 100*min(RVM2)/min(RVM2_raw));

%% ===================== DETECT FALL START (using RAW signals) =====================
t_fall_RVM1 = findFallStart(RVM1_raw, time1, smoothingWindow);
t_fall_RVM2 = findFallStart(RVM2_raw, time2, smoothingWindow);

fprintf('\n=== Fall Detection ===\n');
fprintf('RVM1 fall detected at: %.2f us\n', t_fall_RVM1);
fprintf('RVM2 fall detected at: %.2f us\n', t_fall_RVM2);

%% ===================== TIME ALIGN =====================
time1_aligned = time1 - t_fall_RVM1;
time2_aligned = time2 - t_fall_RVM2;

fprintf('\nTime shift applied:\n');
fprintf('  Scope 1: %.2f us\n', -t_fall_RVM1);
fprintf('  Scope 2: %.2f us\n', -t_fall_RVM2);

%% ===================== CALCULATE COMMON X-AXIS RANGE =====================
x_min = max(min(time1_aligned), min(time2_aligned));
x_max = min(max(time1_aligned), max(time2_aligned));

fprintf('\nCommon x-axis range: %.2f to %.2f us\n', x_min, x_max);

%% ===================== CREATE FIGURE =====================
figure('Name', 'Test 07 - Rigol Scope Data (Time-Aligned, Filtered)', 'Position', [100, 100, 1200, 800]);

% ============ SUBPLOT 1: Rigol 1 (RVM1 & CVR) ============
ax1 = subplot(2, 1, 1);

% Plot RVM1 on left axis
yyaxis left
h1 = plot(time1_aligned, RVM1, 'b-', 'LineWidth', 1);
ylabel('RVM 1 (kV)', 'Color', 'b');
ax1.YColor = 'b';

% Plot CVR on right axis
yyaxis right
h2 = plot(time1_aligned, CVR, 'r-', 'LineWidth', 1);
ylabel('CVR (V)', 'Color', 'r');
ax1.YColor = 'r';

% Mark fall start (t=0)
hold on;
xline(0, 'g--', 'LineWidth', 1.5);
hold off;

xlabel('Time (\mus)');
title('Scope 1: RVM 1 & CVR', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
xlim([x_min, x_max]);

% Fix legend - explicitly specify handles and labels
legend([h1, h2], {'RVM 1', 'CVR'}, 'Location', 'southeast');

% ============ SUBPLOT 2: Rigol 2 (RVM2 & Trigger Sync) ============
ax2 = subplot(2, 1, 2);

% Plot RVM2 on left axis
yyaxis left
h3 = plot(time2_aligned, RVM2, 'b-', 'LineWidth', 1);
ylabel('RVM 2 (kV)', 'Color', 'b');
ax2.YColor = 'b';

% Plot Trigger Sync on right axis
yyaxis right
h4 = plot(time2_aligned, TrigSync, 'r-', 'LineWidth', 1);
ylabel('Trigger Gen Sync (V)', 'Color', 'r');
ax2.YColor = 'r';

% Mark fall start (t=0)
hold on;
xline(0, 'g--', 'LineWidth', 1.5);
hold off;

xlabel('Time (\mus)');
title('Scope 2: RVM 2 & Trigger Generator Sync Output', 'FontSize', 12, 'FontWeight', 'bold');
grid on;
xlim([x_min, x_max]);

% Fix legend - explicitly specify handles and labels
legend([h3, h4], {'RVM 2', 'Trig Sync'}, 'Location', 'southeast');

% ============ Overall Title ============
sgtitle('Test 07 - 6 psi, 55kV (Time-Aligned, Savitzky-Golay Filtered)', 'FontSize', 14, 'FontWeight', 'bold');

%% ===================== DISPLAY STATS =====================
fprintf('\n=== Data Summary (Filtered) ===\n');
fprintf('Scope 1:\n');
fprintf('  RVM 1 range: %.2f to %.2f kV\n', min(RVM1), max(RVM1));
fprintf('  CVR range: %.2f to %.2f V\n', min(CVR), max(CVR));
fprintf('Scope 2:\n');
fprintf('  RVM 2 range: %.2f to %.2f kV\n', min(RVM2), max(RVM2));
fprintf('  Trigger Sync range: %.2f to %.2f V\n', min(TrigSync), max(TrigSync));

%% ===================== HELPER FUNCTION =====================

function t_fall = findFallStart(signal, time, smoothingWindow)
    % FINDFALLSTART - Detect when a signal starts to fall using derivative method
    %
    % Inputs:
    %   signal - The signal array
    %   time - The time array (same size as signal)
    %   smoothingWindow - Number of points for moving average smoothing
    %
    % Output:
    %   t_fall - Time when the fall starts
    
    % Smooth the signal using moving average
    smoothed = movmean(signal, smoothingWindow);
    
    % Calculate derivative
    dt = diff(time);
    dsignal = diff(smoothed);
    derivative = dsignal ./ dt;
    
    % Find index of minimum derivative (steepest fall)
    [~, minDerivIdx] = min(derivative);
    
    % Threshold for "significant" negative derivative (5% of min derivative)
    derivThreshold = min(derivative) * 0.05;
    
    % Search backwards from steepest point to find where falling started
    startIdx = minDerivIdx;
    for i = minDerivIdx:-1:2
        if derivative(i) > derivThreshold
            startIdx = i + 1;
            break;
        end
    end
    
    % Return the time at the fall start
    t_fall = time(startIdx);
end
