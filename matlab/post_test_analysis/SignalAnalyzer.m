% Load the CSV
data = readtable('Test_07_rigol1_20251211_101302.csv');

% Create timetable (Signal Analyzer loves these)
Fs = 10e6;  % 10 MHz sample rate
t0 = -5e-5; % Start time in seconds

ch1 = timetable(data.ch1_v, 'SampleRate', Fs, 'StartTime', seconds(t0));
ch2 = timetable(data.ch2_v, 'SampleRate', Fs, 'StartTime', seconds(t0));

% Open Signal Analyzer
signalAnalyzer(ch1, ch2)