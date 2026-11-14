% load_experiment_data.m
% MATLAB script to load and plot experiment data from the Python GUI logger
%
% Usage:
%   1. Run this script in the 'logs' folder
%   2. It will load the most recent experiment log file
%   3. Creates organized plots of all instrument data

function data = load_experiment_data(filename)
    % If no filename provided, find the most recent log file
    if nargin < 1
        files = dir('experiment_log_*.csv');
        if isempty(files)
            error('No experiment log files found in current directory');
        end
        [~, idx] = max([files.datenum]);
        filename = files(idx).name;
        fprintf('Loading: %s\n', filename);
    end

    % Read the CSV file
    opts = detectImportOptions(filename);
    opts = setvartype(opts, 'notes', 'string');
    data = readtable(filename, opts);

    fprintf('Loaded %d events from %s\n', height(data), filename);
    fprintf('Time range: %.2f to %.2f seconds (%.2f s total)\n', ...
        min(data.timestamp_sec), max(data.timestamp_sec), ...
        max(data.timestamp_sec) - min(data.timestamp_sec));

    % Display event summary
    fprintf('\nEvent Summary:\n');
    event_types = unique(data.event_type);
    for i = 1:length(event_types)
        count = sum(strcmp(data.event_type, event_types{i}));
        fprintf('  %20s: %d events\n', event_types{i}, count);
    end

    % Create plots
    create_plots(data);
end

function create_plots(data)
    % Create comprehensive plots of all instrument data

    figure('Name', 'Experiment Data Overview', 'Position', [100 100 1400 900]);

    % ====================================================================
    % SUBPLOT 1: Arduino Pressure Sensors
    % ====================================================================
    subplot(3, 2, 1);
    arduino_data = data(strcmp(data.event_type, 'ARDUINO_PSI'), :);
    if ~isempty(arduino_data)
        plot(arduino_data.timestamp_sec, str2double(arduino_data.param1), 'r-', 'LineWidth', 1.5);
        hold on;
        plot(arduino_data.timestamp_sec, str2double(arduino_data.param2), 'g-', 'LineWidth', 1.5);
        plot(arduino_data.timestamp_sec, str2double(arduino_data.param3), 'b-', 'LineWidth', 1.5);
        legend('CH0', 'CH1', 'CH2', 'Location', 'best');
        xlabel('Time (s)');
        ylabel('Pressure (PSI)');
        title('SF6 Pressure Sensors');
        grid on;
    else
        title('SF6 Pressure Sensors (No Data)');
    end

    % ====================================================================
    % SUBPLOT 2: WJ Power Supply Voltage
    % ====================================================================
    subplot(3, 2, 2);
    wj_data = data(strcmp(data.event_type, 'WJ_VOLTAGE'), :);
    if ~isempty(wj_data)
        wj1_data = wj_data(strcmp(wj_data.source, 'WJ1'), :);
        wj2_data = wj_data(strcmp(wj_data.source, 'WJ2'), :);

        if ~isempty(wj1_data)
            plot(wj1_data.timestamp_sec, str2double(wj1_data.param1), 'r-', 'LineWidth', 1.5);
            hold on;
        end
        if ~isempty(wj2_data)
            plot(wj2_data.timestamp_sec, str2double(wj2_data.param1), 'b-', 'LineWidth', 1.5);
        end
        legend('WJ1', 'WJ2', 'Location', 'best');
        xlabel('Time (s)');
        ylabel('Voltage (kV)');
        title('WJ Power Supply Voltage');
        grid on;
    else
        title('WJ Power Supply Voltage (No Data)');
    end

    % ====================================================================
    % SUBPLOT 3: WJ Power Supply Current
    % ====================================================================
    subplot(3, 2, 3);
    if ~isempty(wj_data)
        wj1_data = wj_data(strcmp(wj_data.source, 'WJ1'), :);
        wj2_data = wj_data(strcmp(wj_data.source, 'WJ2'), :);

        if ~isempty(wj1_data)
            plot(wj1_data.timestamp_sec, str2double(wj1_data.param2), 'r-', 'LineWidth', 1.5);
            hold on;
        end
        if ~isempty(wj2_data)
            plot(wj2_data.timestamp_sec, str2double(wj2_data.param2), 'b-', 'LineWidth', 1.5);
        end
        legend('WJ1', 'WJ2', 'Location', 'best');
        xlabel('Time (s)');
        ylabel('Current (mA)');
        title('WJ Power Supply Current');
        grid on;
    else
        title('WJ Power Supply Current (No Data)');
    end

    % ====================================================================
    % SUBPLOT 4: Event Timeline
    % ====================================================================
    subplot(3, 2, 4);

    % Plot pulse events as vertical lines
    dg535_pulses = data(strcmp(data.event_type, 'DG535_PULSE'), :);
    bnc575_pulses = data(strcmp(data.event_type, 'BNC575_PULSE'), :);
    scope_captures = data(strcmp(data.event_type, 'SCOPE_ALL'), :);

    ylim([0 4]);
    hold on;

    if ~isempty(dg535_pulses)
        for i = 1:height(dg535_pulses)
            plot([dg535_pulses.timestamp_sec(i) dg535_pulses.timestamp_sec(i)], [0.5 1.5], 'r-', 'LineWidth', 2);
        end
    end

    if ~isempty(bnc575_pulses)
        for i = 1:height(bnc575_pulses)
            plot([bnc575_pulses.timestamp_sec(i) bnc575_pulses.timestamp_sec(i)], [1.5 2.5], 'g-', 'LineWidth', 2);
        end
    end

    if ~isempty(scope_captures)
        for i = 1:height(scope_captures)
            plot([scope_captures.timestamp_sec(i) scope_captures.timestamp_sec(i)], [2.5 3.5], 'b-', 'LineWidth', 2);
        end
    end

    set(gca, 'YTick', [1 2 3], 'YTickLabel', {'DG535', 'BNC575', 'SCOPE'});
    xlabel('Time (s)');
    title('Pulse Events Timeline');
    grid on;

    % ====================================================================
    % SUBPLOT 5: Arduino Switch States
    % ====================================================================
    subplot(3, 2, 5);
    switch_data = data(strcmp(data.event_type, 'ARDUINO_SWITCH'), :);
    if ~isempty(switch_data)
        unique_switches = unique(switch_data.param1);
        hold on;
        colors = lines(length(unique_switches));

        for i = 1:length(unique_switches)
            sw_idx = unique_switches(i);
            sw_events = switch_data(strcmp(switch_data.param1, sw_idx), :);

            for j = 1:height(sw_events)
                state = str2double(sw_events.param2(j));
                if state == 1
                    plot(sw_events.timestamp_sec(j), str2double(sw_idx), 'o', ...
                        'MarkerSize', 8, 'MarkerFaceColor', colors(i,:), ...
                        'MarkerEdgeColor', 'k');
                end
            end
        end

        xlabel('Time (s)');
        ylabel('Switch Index');
        title('Arduino Switch Events (ON)');
        grid on;
    else
        title('Arduino Switch Events (No Data)');
    end

    % ====================================================================
    % SUBPLOT 6: WJ HV Status
    % ====================================================================
    subplot(3, 2, 6);
    if ~isempty(wj_data)
        wj1_data = wj_data(strcmp(wj_data.source, 'WJ1'), :);
        wj2_data = wj_data(strcmp(wj_data.source, 'WJ2'), :);

        hold on;
        if ~isempty(wj1_data)
            hv_status = str2double(wj1_data.param3);
            plot(wj1_data.timestamp_sec, hv_status, 'r-', 'LineWidth', 1.5);
        end
        if ~isempty(wj2_data)
            hv_status = str2double(wj2_data.param3);
            plot(wj2_data.timestamp_sec, hv_status, 'b-', 'LineWidth', 1.5);
        end

        legend('WJ1 HV', 'WJ2 HV', 'Location', 'best');
        xlabel('Time (s)');
        ylabel('HV Status (0=OFF, 1=ON)');
        title('WJ High Voltage Status');
        ylim([-0.1 1.1]);
        grid on;
    else
        title('WJ High Voltage Status (No Data)');
    end

    sgtitle('Experiment Data Overview', 'FontSize', 14, 'FontWeight', 'bold');
end

function export_filtered_data(data, event_type, output_filename)
    % Export specific event types to separate CSV files
    %
    % Example:
    %   export_filtered_data(data, 'ARDUINO_PSI', 'arduino_pressure.csv');

    filtered = data(strcmp(data.event_type, event_type), :);
    writetable(filtered, output_filename);
    fprintf('Exported %d %s events to %s\n', height(filtered), event_type, output_filename);
end

% Auto-run if called as script
if ~nargout
    data = load_experiment_data();
end
