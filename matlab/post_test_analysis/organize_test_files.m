%% Organize Test CSV Files - With Experiment Logs
% This script parses a log file, extracts test information and associated
% CSV files (rigol + experiment logs), creates folders for each test, 
% and copies/renames files accordingly.
%
% INSTRUCTIONS:
% 1. Save your log text to a file called 'test_log.txt' in your data folder
% 2. Update 'baseFolder' below to match your data folder path
% 3. Run this script

clear; clc;

%% ===================== CONFIGURATION =====================
% Set the base folder where CSV files are located
baseFolder = 'C:\Users\ESpurbeck\Desktop\LANL Project\Marx Testing\Testing\12.11.25';

% Set the path to the log file
logFilePath = fullfile(baseFolder, 'Testing 12_11_25.txt');

% Set to true to actually copy files, false for dry run (preview only)
doCopy = true;

%% ===================== READ LOG FILE =====================
if ~exist(logFilePath, 'file')
    error('Log file not found: %s\nPlease save your log text to this file.', logFilePath);
end

logText = fileread(logFilePath);
fprintf('Reading log file: %s\n\n', logFilePath);

%% ===================== PARSE LOG FILE =====================
% Split into lines and clean up
lines = strsplit(logText, {'\n', '\r'});
lines = lines(~cellfun(@isempty, strtrim(lines))); % Remove empty lines

% Initialize storage
tests = struct('number', {}, 'description', {}, 'csvFiles', {}, 'expLogFile', {}, 'folderName', {});
currentTestIdx = 0;
collectingCsv = false;

for i = 1:length(lines)
    line = strtrim(lines{i});
    
    % Check for test header patterns:
    % "Test1 : 6psi" or "Test 2: 6 psi..." or "Test 19: 13 psi..."
    testMatch = regexp(line, '^Test\s*(\d+)\s*[:\s]+(.*)$', 'tokens', 'ignorecase');
    
    if ~isempty(testMatch)
        % New test found
        currentTestIdx = currentTestIdx + 1;
        testNum = str2double(testMatch{1}{1});
        testDesc = strtrim(testMatch{1}{2});
        
        % Clean description for folder name
        cleanDesc = testDesc;
        cleanDesc = regexprep(cleanDesc, '[<>:"/\\|?*]', ''); % Remove invalid chars
        cleanDesc = regexprep(cleanDesc, '\s+', '_'); % Spaces to underscores
        cleanDesc = regexprep(cleanDesc, '_+', '_'); % Multiple underscores to single
        cleanDesc = regexprep(cleanDesc, '^_|_$', ''); % Remove leading/trailing
        
        % Truncate if too long
        if length(cleanDesc) > 60
            cleanDesc = cleanDesc(1:60);
        end
        
        tests(currentTestIdx).number = testNum;
        tests(currentTestIdx).description = testDesc;
        tests(currentTestIdx).csvFiles = {};
        tests(currentTestIdx).expLogFile = '';
        
        if isempty(cleanDesc)
            tests(currentTestIdx).folderName = sprintf('Test_%02d', testNum);
        else
            tests(currentTestIdx).folderName = sprintf('Test_%02d_%s', testNum, cleanDesc);
        end
        
        collectingCsv = false;
        continue;
    end
    
    % Check for DATA LOGGER line to get experiment log filename
    if currentTestIdx > 0
        logMatch = regexp(line, '\[DATA LOGGER\].*?(experiment_log_\d+_\d+\.csv)', 'tokens');
        if ~isempty(logMatch)
            tests(currentTestIdx).expLogFile = logMatch{1}{1};
            continue;
        end
    end
    
    % Check for "Saved:" marker
    if strcmpi(line, 'Saved:')
        collectingCsv = true;
        continue;
    end
    
    % Collect CSV filenames
    if collectingCsv && currentTestIdx > 0
        csvMatch = regexp(line, '^(rigol\d+_\d+_\d+\.csv)$', 'tokens');
        if ~isempty(csvMatch)
            tests(currentTestIdx).csvFiles{end+1} = csvMatch{1}{1};
        else
            % Stop collecting if we hit a non-CSV line
            collectingCsv = false;
        end
    end
end

%% ===================== DISPLAY SUMMARY =====================
fprintf('========================================\n');
fprintf('  PARSED %d TESTS\n', length(tests));
fprintf('========================================\n\n');

for i = 1:length(tests)
    fprintf('Test %02d:\n', tests(i).number);
    fprintf('  Description: %s\n', tests(i).description);
    fprintf('  Folder: %s\n', tests(i).folderName);
    fprintf('  Experiment Log: %s\n', tests(i).expLogFile);
    fprintf('  Rigol CSV Files (%d):\n', length(tests(i).csvFiles));
    for j = 1:length(tests(i).csvFiles)
        fprintf('    %d. %s\n', j, tests(i).csvFiles{j});
    end
    fprintf('\n');
end

%% ===================== CREATE FOLDERS AND COPY FILES =====================
if ~doCopy
    fprintf('*** DRY RUN MODE - No files will be copied ***\n');
    fprintf('Set doCopy = true to actually copy files.\n\n');
end

fprintf('========================================\n');
fprintf('  CREATING FOLDERS AND COPYING FILES\n');
fprintf('========================================\n\n');

successCount = 0;
warningCount = 0;

for i = 1:length(tests)
    folderPath = fullfile(baseFolder, tests(i).folderName);
    
    % Create folder
    if doCopy
        if ~exist(folderPath, 'dir')
            mkdir(folderPath);
            fprintf('[CREATED] %s\n', tests(i).folderName);
        else
            fprintf('[EXISTS]  %s\n', tests(i).folderName);
        end
    else
        fprintf('[FOLDER]  %s\n', tests(i).folderName);
    end
    
    % Copy experiment log file
    if ~isempty(tests(i).expLogFile)
        srcFileName = tests(i).expLogFile;
        srcPath = fullfile(baseFolder, srcFileName);
        
        % Create new filename: Test_XX_experiment_log.csv
        newFileName = sprintf('Test_%02d_experiment_log.csv', tests(i).number);
        dstPath = fullfile(folderPath, newFileName);
        
        if exist(srcPath, 'file')
            if doCopy
                copyfile(srcPath, dstPath);
                fprintf('  [COPIED]  %s -> %s\n', srcFileName, newFileName);
            else
                fprintf('  [COPY]    %s -> %s\n', srcFileName, newFileName);
            end
            successCount = successCount + 1;
        else
            fprintf('  [WARNING] Experiment log not found: %s\n', srcFileName);
            warningCount = warningCount + 1;
        end
    end
    
    % Copy each rigol CSV file
    for j = 1:length(tests(i).csvFiles)
        srcFileName = tests(i).csvFiles{j};
        srcPath = fullfile(baseFolder, srcFileName);
        
        % Create new filename: Test_XX_rigolY.csv
        rigolMatch = regexp(srcFileName, 'rigol(\d+)_(\d+)_(\d+)\.csv', 'tokens');
        if ~isempty(rigolMatch)
            rigolNum = rigolMatch{1}{1};
            timestamp = [rigolMatch{1}{2} '_' rigolMatch{1}{3}];
            newFileName = sprintf('Test_%02d_rigol%s_%s.csv', tests(i).number, rigolNum, timestamp);
        else
            newFileName = sprintf('Test_%02d_%s', tests(i).number, srcFileName);
        end
        
        dstPath = fullfile(folderPath, newFileName);
        
        if exist(srcPath, 'file')
            if doCopy
                copyfile(srcPath, dstPath);
                fprintf('  [COPIED]  %s -> %s\n', srcFileName, newFileName);
            else
                fprintf('  [COPY]    %s -> %s\n', srcFileName, newFileName);
            end
            successCount = successCount + 1;
        else
            fprintf('  [WARNING] File not found: %s\n', srcFileName);
            warningCount = warningCount + 1;
        end
    end
    fprintf('\n');
end

%% ===================== FINAL SUMMARY =====================
fprintf('========================================\n');
fprintf('  SUMMARY\n');
fprintf('========================================\n');
fprintf('Tests processed: %d\n', length(tests));
fprintf('Files copied:    %d\n', successCount);
fprintf('Warnings:        %d\n', warningCount);

if ~doCopy
    fprintf('\n*** This was a DRY RUN - no files were actually copied ***\n');
    fprintf('Set doCopy = true and run again to copy files.\n');
end

fprintf('\nDone!\n');
