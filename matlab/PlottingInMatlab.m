%=== Load Rigol CSV ===%
data = readtable('rigol_20250101_120000.csv');   % <-- change filename

t   = data.time_s;   % time in seconds
v1  = data.ch1_v;    % channel 1
v2  = data.ch2_v;    % channel 2

%=== Create Dual-Y Plot ===%
figure;
yyaxis left
plot(t, v1, 'b-', 'LineWidth', 1.5);
ylabel('Channel 1 Voltage (V)');
grid on;

yyaxis right
plot(t, v2, 'r-', 'LineWidth', 1.5);
ylabel('Channel 2 Voltage (V)');

xlabel('Time (s)');
title('Rigol Dual-Channel Waveform');
legend('CH1','CH2');
