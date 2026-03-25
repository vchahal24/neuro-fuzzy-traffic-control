function [rmse, mae, predMin, predMax, targetMin, targetMax] = compute_metrics(yTrue, yPred)
  % computes the core regression metrics for prediction quality checks
  err = yPred(:) - yTrue(:);
  rmse = sqrt(mean(err .^ 2));
  mae = mean(abs(err));

  % range checks help confirm prediction scale is close to target scale
  predMin = min(yPred);
  predMax = max(yPred);
  targetMin = min(yTrue);
  targetMax = max(yTrue);
end
