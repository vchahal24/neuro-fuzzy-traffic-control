pkg load fuzzy-logic-toolkit;

% parse two CLI inputs: queue_total_norm and imbalance
args = argv();
if numel(args) < 2
  error('Expected args: queue_total_norm imbalance');
end

queueTotalNorm = str2double(args{1});
imbalance = str2double(args{2});
if any(isnan([queueTotalNorm, imbalance]))
  error('Arguments must be numeric.');
end

% keep FIS path relative to this script location
scriptDir = fileparts(mfilename('fullpath'));
fisPath = fullfile(scriptDir, 'traffic_ns_split_trained.fis');

% evaluate trained FIS for one state and print only the numeric prediction
fis = readfis(fisPath);
nsRatio = evalfis([queueTotalNorm, imbalance], fis);
fprintf('%.10f\n', nsRatio);
