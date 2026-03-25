pkg load fuzzy-logic-toolkit;

% local path setup so helper functions resolve cleanly
scriptDir = fileparts(mfilename('fullpath'));
addpath(scriptDir);

% default inputs (override here if needed)
trainingCsvPath = fullfile(scriptDir, '..', 'outputs', 'experiments', 'training_v1', 'cycle_training_data.csv');
fisPath = fullfile(scriptDir, 'traffic_ns_split_trained.fis');
controllerFilter = 'baseline_proportional'; % e.g. 'baseline_proportional' or '' for all rows

% optional prediction export
savePredictionsCsv = true;
predictionsCsvPath = fullfile(scriptDir, 'trained_fis_predictions.csv');

fprintf('Training CSV: %s\n', trainingCsvPath);
fprintf('FIS path: %s\n', fisPath);

% loads supervised rows, runs FIS inference, then computes summary metrics
[x, y, rowsUsed] = load_training_xy(trainingCsvPath, controllerFilter);
fis = readfis(fisPath);
yPred = evalfis(x, fis);

[rmse, mae, predMin, predMax, targetMin, targetMax] = compute_metrics(y, yPred);

fprintf('\n=== Trained FIS Evaluation ===\n');
fprintf('Rows used: %d\n', rowsUsed);
fprintf('RMSE: %.6f\n', rmse);
fprintf('MAE: %.6f\n', mae);
fprintf('Pred min/max: %.6f / %.6f\n', predMin, predMax);
fprintf('Target min/max: %.6f / %.6f\n', targetMin, targetMax);

if savePredictionsCsv
  write_prediction_csv(predictionsCsvPath, x, y, yPred);
  fprintf('Saved predictions: %s\n', predictionsCsvPath);
end
