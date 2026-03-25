pkg load fuzzy-logic-toolkit;

% resolve FIS path from this script folder
scriptDir = fileparts(mfilename('fullpath'));
fisPath = fullfile(scriptDir, 'traffic_ns_split_init.fis');

% quick file existence check before loading
% helpful when relative-path issues happen in Octave
fprintf('FIS path: %s\n', fisPath);
fprintf('FIS exists: %d\n', exist(fisPath, 'file'));

fis = readfis(fisPath);
fprintf('Loaded FIS successfully\n');

% smoke-test a few representative states
x1 = [0.20, 0.00];
y1 = evalfis(x1, fis);
fprintf('Test 1 (low queue, balanced): %.10f\n', y1);

x2 = [0.90, 0.70];
y2 = evalfis(x2, fis);
fprintf('Test 2 (high queue, NS heavy): %.10f\n', y2);

x3 = [0.90, -0.70];
y3 = evalfis(x3, fis);
fprintf('Test 3 (high queue, EW heavy): %.10f\n', y3);
