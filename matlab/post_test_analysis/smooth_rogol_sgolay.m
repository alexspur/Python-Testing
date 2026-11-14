%% Smooth Rigol Oscilloscope Data - Savitzky-Golay Filter
% Applies Savitzky-Golay smoothing to CSV data from Rigol oscilloscope

%% Load Data
filename = 'Test_07_rigol1_20251211_101302.csv';
data = readtable(filename);

time = data.time_s;
ch1 = data.ch1_v;
ch2 = data.ch2_v;

%% Apply Savitzky-Golay Smoothing
% Parameters: window size (must be odd), polynomial order
window_size = 21;  % Must be odd number
poly_order = 3;    % Polynomial order (must be < window_size)

ch1_smooth = sgolayfilt(ch1, poly_order, window_size);
ch2_smooth = sgolayfilt(ch2, poly_order, window_size);

%% Plot Results
figure('Position', [100 100 1200 800]);

% Channel 1
subplot(2,2,1)
plot(time*1e6, ch1, 'b-', 'LineWidth', 0.5, 'DisplayName', 'Original')
hold on
plot(time*1e6, ch1_smooth, 'g-', 'LineWidth', 1.5, 'DisplayName', 'Smoothed')
xlabel('Time (μs)')
ylabel('Voltage (V)')
title('Channel 1')
legend('Location', 'best')
grid on

% Channel 2
subplot(2,2,2)
plot(time*1e6, ch2, 'b-', 'LineWidth', 0.5, 'DisplayName', 'Original')
hold on
plot(time*1e6, ch2_smooth, 'g-', 'LineWidth', 1.5, 'DisplayName', 'Smoothed')
xlabel('Time (μs)')
ylabel('Voltage (V)')
title('Channel 2')
legend('Location', 'best')
grid on

% Zoomed view Channel 2
subplot(2,2,3)
idx = 200:400;  % Zoom region
plot(time(idx)*1e6, ch2(idx), 'b-', 'LineWidth', 1, 'DisplayName', 'Original')
hold on
plot(time(idx)*1e6, ch2_smooth(idx), 'g-', 'LineWidth', 2, 'DisplayName', 'Smoothed')
xlabel('Time (μs)')
ylabel('Voltage (V)')
title('Channel 2 - Zoomed')
legend('Location', 'best')
grid on

% Both channels smoothed
subplot(2,2,4)
plot(time*1e6, ch1_smooth, 'r-', 'LineWidth', 1.5, 'DisplayName', 'Ch1 Smoothed')
hold on
plot(time*1e6, ch2_smooth, 'b-', 'LineWidth', 1.5, 'DisplayName', 'Ch2 Smoothed')
xlabel('Time (μs)')
ylabel('Voltage (V)')
title('Both Channels (Smoothed)')
legend('Location', 'best')
grid on

sgtitle(sprintf('Savitzky-Golay Smoothed (window=%d, order=%d)', window_size, poly_order))

%% Export smoothed data (optional)
smoothed_data = table(time, ch1_smooth, ch2_smooth, ...
    'VariableNames', {'time_s', 'ch1_v_smooth', 'ch2_v_smooth'});
writetable(smoothed_data, 'Test_07_rigol1_sgolay_smoothed.csv');
disp('Smoothed data saved to Test_07_rigol1_sgolay_smoothed.csv')

%% For Signal Analyzer - create timetables
Fs = 10e6;  % 10 MHz sample rate
t0 = seconds(time(1));

ch1_tt = timetable(ch1_smooth, 'SampleRate', Fs, 'StartTime', t0);
ch2_tt = timetable(ch2_smooth, 'SampleRate', Fs, 'StartTime', t0);

% Uncomment to open in Signal Analyzer:
% signalAnalyzer(ch1_tt, ch2_tt)
