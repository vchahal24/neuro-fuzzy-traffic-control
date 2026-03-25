pkg load fuzzy-logic-toolkit;

% local path setup so helper functions resolve cleanly
scriptDir = fileparts(mfilename('fullpath'));
addpath(scriptDir);

% default inputs (override here if needed)
trainingCsvPath = fullfile(scriptDir, '..', 'outputs', 'experiments', 'training_v1', 'cycle_training_data.csv');
initialFisPath = fullfile(scriptDir, 'traffic_ns_split_init.fis');
trainedFisPath = fullfile(scriptDir, 'traffic_ns_split_trained.fis');
controllerFilter = 'baseline_proportional'; % e.g. 'baseline_proportional' or '' for all rows
maxRows = 5000; % set finite (e.g. 5000) for faster local sweeps
progressEvery = 50; % print progress every N tested combinations

fprintf('Training CSV: %s\n', trainingCsvPath);
fprintf('Initial FIS: %s\n', initialFisPath);

[x, y, rowsUsed] = load_training_xy(trainingCsvPath, controllerFilter);
if isfinite(maxRows)
  % optional random cap for quicker local tuning runs
  cappedRows = min(rowsUsed, maxRows);
  rngSeed = 4430;
  rand('seed', rngSeed);
  subsetIdx = randperm(rowsUsed, cappedRows);
  x = x(subsetIdx, :);
  y = y(subsetIdx, :);
  rowsUsed = cappedRows;
end
baseFis = readfis(initialFisPath);

% small explainable search grid for membership and output constants
input1MediumCenterCandidates = [0.45, 0.50, 0.55];
input1MediumWidthCandidates = [0.20, 0.25];
input2BalancedWidthCandidates = [0.15, 0.20, 0.25];

outVeryShortCandidates = [0.18, 0.20];
outShortCandidates = [0.33, 0.35];
outMediumCandidates = [0.48, 0.50];
outLongCandidates = [0.65, 0.67];
outVeryLongCandidates = [0.80, 0.82];

bestRmse = inf;
bestMae = inf;
bestFis = baseFis;
bestParams = struct();
tested = 0;

% brute-force all candidate combinations
for centerVal = input1MediumCenterCandidates
  for widthVal = input1MediumWidthCandidates
    leftVal = centerVal - widthVal;
    rightVal = centerVal + widthVal;
    if !(leftVal < centerVal && centerVal < rightVal)
      continue;
    end

    for balanceWidth = input2BalancedWidthCandidates
      for veryShortVal = outVeryShortCandidates
        for shortVal = outShortCandidates
          for mediumVal = outMediumCandidates
            for longVal = outLongCandidates
              for veryLongVal = outVeryLongCandidates
                if !(veryShortVal < shortVal && shortVal < mediumVal && mediumVal < longVal && longVal < veryLongVal)
                  continue;
                end

                testFis = baseFis;

                % input 1 medium trimf [left center right]
                testFis.input(1).mf(2).params = [leftVal, centerVal, rightVal];

                % input 2 balanced trimf [-width 0 width]
                testFis.input(2).mf(2).params = [-balanceWidth, 0.0, balanceWidth];

                % sugeno constant outputs [veryshort short medium long verylong]
                testFis.output(1).mf(1).params = [veryShortVal];
                testFis.output(1).mf(2).params = [shortVal];
                testFis.output(1).mf(3).params = [mediumVal];
                testFis.output(1).mf(4).params = [longVal];
                testFis.output(1).mf(5).params = [veryLongVal];

                yPred = evalfis(x, testFis);
                err = yPred(:) - y(:);
                rmse = sqrt(mean(err .^ 2));
                mae = mean(abs(err));

                tested = tested + 1;
                if rmse < bestRmse
                  bestRmse = rmse;
                  bestMae = mae;
                  bestFis = testFis;
                  bestParams.input1Medium = [leftVal, centerVal, rightVal];
                  bestParams.input2Balanced = [-balanceWidth, 0.0, balanceWidth];
                  bestParams.outVeryShort = veryShortVal;
                  bestParams.outShort = shortVal;
                  bestParams.outMedium = mediumVal;
                  bestParams.outLong = longVal;
                  bestParams.outVeryLong = veryLongVal;

                  % checkpoint the current best model immediately
                  write_fis_exact_path(bestFis, trainedFisPath);

                  fprintf(['NEW BEST @ tested=%d | RMSE=%.6f | MAE=%.6f | ' ...
                    'Input1_Medium=[%.4f %.4f %.4f] | Input2_Balanced=[%.4f %.4f %.4f] | ' ...
                    'Outputs=[%.4f %.4f %.4f %.4f %.4f]\n'], ...
                    tested, bestRmse, bestMae, ...
                    bestParams.input1Medium(1), bestParams.input1Medium(2), bestParams.input1Medium(3), ...
                    bestParams.input2Balanced(1), bestParams.input2Balanced(2), bestParams.input2Balanced(3), ...
                    bestParams.outVeryShort, bestParams.outShort, bestParams.outMedium, bestParams.outLong, bestParams.outVeryLong);
                end

                if progressEvery > 0 && mod(tested, progressEvery) == 0
                  fprintf('Progress: tested=%d | best_rmse=%.6f | best_mae=%.6f\n', tested, bestRmse, bestMae);
                end
              end
            end
          end
        end
      end
    end
  end
end

fprintf('\n=== Grid Search Done ===\n');
fprintf('Rows used: %d\n', rowsUsed);
fprintf('Tested combinations: %d\n', tested);
fprintf('Best RMSE: %.6f\n', bestRmse);
fprintf('Best MAE: %.6f\n', bestMae);
fprintf('Best Input1 Medium trimf: [%.4f %.4f %.4f]\n', bestParams.input1Medium(1), bestParams.input1Medium(2), bestParams.input1Medium(3));
fprintf('Best Input2 Balanced trimf: [%.4f %.4f %.4f]\n', bestParams.input2Balanced(1), bestParams.input2Balanced(2), bestParams.input2Balanced(3));
fprintf('Best outputs [VeryShort Short Medium Long VeryLong]: [%.4f %.4f %.4f %.4f %.4f]\n', ...
  bestParams.outVeryShort, bestParams.outShort, bestParams.outMedium, bestParams.outLong, bestParams.outVeryLong);

write_fis_exact_path(bestFis, trainedFisPath);
fprintf('Saved tuned FIS: %s\n', trainedFisPath);
